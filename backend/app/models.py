"""Shared domain model for the architecture graph.

The scanner produces :class:`ScannedNode` and :class:`ScannedEdge` objects,
which are persisted to Neo4j and later re-emitted to the frontend in the
react-force-graph shape ({nodes: [...], links: [...]}).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    """Node categories used across the whole application.

    They are split into two abstraction levels:

    * Architecture (top-level): ``Application``, ``Client``, ``Database`` and
      ``ExternalAPI`` — the only nodes shown in the default network map.
    * Internal (drill-down): ``Service`` (a file / module) and ``Endpoint``
      (an exposed HTTP route), which hang off an ``Application`` as children.
    """

    # --- architecture level ------------------------------------------------
    APPLICATION = "Application"    # logical app / microservice (parent node)
    CLIENT = "Client"              # end user / inbound caller
    DATABASE = "Database"          # a SQL / NoSQL / cache connection
    EXTERNAL_API = "ExternalAPI"   # a third party API call
    # --- internal (child) level -------------------------------------------
    SERVICE = "Service"            # internal file / module
    ENDPOINT = "Endpoint"          # an exposed HTTP route


class EdgeType(str, Enum):
    """Relationship categories between nodes."""

    CALLS = "CALLS"                  # Service -> Service (import / invocation)
    EXPOSES = "EXPOSES"              # Service -> Endpoint
    QUERIES = "QUERIES"              # (Service|Application) -> Database
    REQUESTS = "REQUESTS"            # (Service|Application) -> ExternalAPI
    HAS_COMPONENT = "HAS_COMPONENT"  # Application -> Service (parent/child)
    USES = "USES"                    # Client -> Application (inbound flow)


@dataclass(slots=True)
class ScannedNode:
    """A single discovered entity.

    ``id`` is a deterministic, stable key so re-scanning the same codebase
    never creates duplicates (we MERGE on it in Neo4j).
    """

    id: str
    type: NodeType
    name: str
    file_path: str
    line: int | None = None
    snippet: str | None = None
    # --- hierarchy ---------------------------------------------------------
    # id of the parent Application (children) or None for architecture nodes.
    parent_id: str | None = None
    # "architecture" (top level) or "internal" (child components).
    level: str = "internal"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_props(self) -> dict[str, Any]:
        """Flatten to the property map stored on the Neo4j node."""
        props: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "filePath": self.file_path,
            "line": self.line,
            "snippet": self.snippet,
            "parentId": self.parent_id,
            "level": self.level,
        }
        # Arbitrary extra metadata (e.g. HTTP method, db engine) stored as a
        # JSON-encoded string to keep the Neo4j property model simple.
        import json

        props["meta"] = json.dumps(self.meta) if self.meta else None
        return props


@dataclass(slots=True)
class ScannedEdge:
    """A directed relationship between two nodes (referenced by id)."""

    source: str
    target: str
    type: EdgeType
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanResult:
    """Everything the scanner found in a single codebase."""

    nodes: list[ScannedNode] = field(default_factory=list)
    edges: list[ScannedEdge] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0

    def merge(self, other: "ScanResult") -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.files_scanned += other.files_scanned
        self.files_skipped += other.files_skipped
