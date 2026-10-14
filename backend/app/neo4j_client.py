"""Thin async wrapper around the official Neo4j Python driver.

Responsibilities:
  * manage the driver lifecycle (created/destroyed by FastAPI startup hook)
  * create indexes / uniqueness constraints for our node categories
  * persist a :class:`ScanResult` (nodes + edges) idempotently
  * read the whole graph back in the shape the frontend expects
"""
from __future__ import annotations

import json
import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver

from .config import settings
from .models import EdgeType, NodeType, ScanResult

logger = logging.getLogger("vectograph.neo4j")


class Neo4jClient:
    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    # -- lifecycle -----------------------------------------------------------
    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await self._driver.verify_connectivity()
        await self._init_schema()
        logger.info("Connected to Neo4j at %s", settings.neo4j_uri)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not initialised")
        return self._driver

    # -- schema --------------------------------------------------------------
    async def _init_schema(self) -> None:
        """Create a uniqueness constraint per label.

        The scanner generates stable ids, so a uniqueness constraint makes the
        MERGE operations both correct and fast.
        """
        async with self.driver.session() as session:
            for label in NodeType:
                await session.run(
                    f"CREATE CONSTRAINT {label.value.lower()}_id IF NOT EXISTS "
                    f"FOR (n:{label.value}) REQUIRE n.id IS UNIQUE"
                )
            # Speed up parent/child drill-down lookups.
            await session.run(
                "CREATE INDEX service_parent IF NOT EXISTS "
                "FOR (n:Service) ON (n.parentId)"
            )
            await session.run(
                "CREATE INDEX endpoint_parent IF NOT EXISTS "
                "FOR (n:Endpoint) ON (n.parentId)"
            )

    # -- writes --------------------------------------------------------------
    async def clear_graph(self) -> None:
        """Delete the whole graph (used before each upload for an MVP)."""
        async with self.driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")

    async def write_scan(self, result: ScanResult) -> dict[str, int]:
        """Persist nodes then edges. Returns counts for the API response."""
        async with self.driver.session() as session:
            for node in result.nodes:
                await session.run(
                    f"MERGE (n:{node.type.value} {{id: $id}}) SET n += $props",
                    id=node.id,
                    props=node.to_props(),
                )

            for edge in result.edges:
                # Nodes always exist because we wrote all of them above. The
                # WHERE clause guards against any dangling reference.
                await session.run(
                    f"MATCH (a {{id: $src}}), (b {{id: $dst}}) "
                    f"MERGE (a)-[r:{edge.type.value}]->(b)",
                    src=edge.source,
                    dst=edge.target,
                )

        return {
            "nodes": len(result.nodes),
            "edges": len(result.edges),
        }

    # -- reads ---------------------------------------------------------------
    async def fetch_graph(self) -> dict[str, Any]:
        """Return the entire (hierarchical) graph in react-force-graph format.

        Nodes carry their type *and* their abstraction level (``level``) plus a
        ``parentId`` for child components, so the frontend can derive both the
        high-level network map and the per-application drill-down view from a
        single payload. ``applications`` is a convenience index for the UI.
        """
        nodes: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        async with self.driver.session() as session:
            # --- nodes ------------------------------------------------------
            node_result = await session.run(
                "MATCH (n) WHERE n.id IS NOT NULL RETURN n, labels(n) AS labels"
            )
            async for record in node_result:
                node = record["n"]
                props = dict(node)
                node_id = props.get("id")
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                nodes.append(
                    {
                        "id": node_id,
                        "name": props.get("name", node_id),
                        "type": props.get("type", (record["labels"] or ["Service"])[0]),
                        "level": props.get("level", "internal"),
                        "parentId": props.get("parentId"),
                        "filePath": props.get("filePath"),
                        "line": props.get("line"),
                        "snippet": props.get("snippet"),
                        "meta": _safe_json(props.get("meta")),
                    }
                )

            # --- links (includes HAS_COMPONENT parent/child edges) ----------
            edge_result = await session.run(
                "MATCH (a)-[r]->(b) "
                "WHERE a.id IS NOT NULL AND b.id IS NOT NULL "
                "RETURN a.id AS source, b.id AS target, type(r) AS type"
            )
            async for record in edge_result:
                links.append(
                    {
                        "source": record["source"],
                        "target": record["target"],
                        "type": record["type"],
                    }
                )

        # Count children per application directly from the containment edges.
        child_counts: dict[str, int] = {}
        for link in links:
            if link["type"] == EdgeType.HAS_COMPONENT.value:
                child_counts[link["source"]] = child_counts.get(link["source"], 0) + 1

        applications: list[dict[str, Any]] = []
        for node in nodes:
            if node["type"] != NodeType.APPLICATION.value:
                continue
            applications.append(
                {
                    "id": node["id"],
                    "name": node["name"],
                    "filePath": node["filePath"],
                    "components": child_counts.get(node["id"], 0),
                    "meta": node["meta"],
                }
            )

        return {"nodes": nodes, "links": links, "applications": applications}


def _safe_json(value: Any) -> dict[str, Any]:
    """Decode the meta property, tolerating missing / malformed values."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


# A single shared client instance for the process.
neo4j_client = Neo4jClient()
