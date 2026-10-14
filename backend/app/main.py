"""Vectograph API entrypoint.

Exposes:
  GET  /api/health   - liveness + Neo4j connectivity
  POST /api/upload   - receive a .zip, scan it, persist the graph
  GET  /api/graph    - return the whole graph for the frontend
  DELETE /api/graph  - wipe the graph
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .archive import UnsafeArchiveError, extracted_archive
from .config import settings
from .neo4j_client import neo4j_client
from .scanner.engine import scan_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vectograph.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup -----------------------------------------------------------
    try:
        await neo4j_client.connect()
    except Exception as exc:  # pragma: no cover - depends on external service
        # Don't crash the API: the health endpoint surfaces the problem and
        # Docker's restart policy / health check will bring Neo4j up shortly.
        logger.error("Could not connect to Neo4j at startup: %s", exc)
    yield
    # --- shutdown ----------------------------------------------------------
    await neo4j_client.close()


app = FastAPI(
    title="Vectograph API",
    description="Cybersecurity architecture mapping: scan a codebase into a graph.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    """Report whether the backend can reach Neo4j."""
    try:
        async with neo4j_client.driver.session() as session:
            await session.run("RETURN 1")
        return {"status": "ok", "neo4j": "up"}
    except Exception as exc:  # pragma: no cover
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "neo4j": "down", "detail": str(exc)},
        )


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept a .zip codebase, scan it and persist the resulting graph."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {settings.max_upload_mb} MB limit.",
        )

    # --- scan (CPU-bound, but fast enough for an MVP to stay async) --------
    try:
        with extracted_archive(payload) as root:
            result = scan_directory(root)
    except UnsafeArchiveError as exc:
        raise HTTPException(status_code=400, detail=f"Unsafe archive: {exc}") from exc
    except Exception as exc:  # pragma: no cover - corrupt zip etc.
        logger.exception("Scan failed")
        raise HTTPException(status_code=400, detail=f"Could not scan archive: {exc}") from exc

    # --- persist -----------------------------------------------------------
    try:
        # MVP semantics: each upload replaces the previous graph so the user
        # always sees exactly the codebase they just analysed.
        await neo4j_client.clear_graph()
        counts = await neo4j_client.write_scan(result)
    except Exception as exc:  # pragma: no cover
        logger.exception("Neo4j write failed")
        raise HTTPException(
            status_code=503, detail=f"Could not store graph: {exc}"
        ) from exc

    # --- summary -----------------------------------------------------------
    by_type: dict[str, int] = {}
    for node in result.nodes:
        by_type[node.type.value] = by_type.get(node.type.value, 0) + 1

    return {
        "status": "success",
        "filesScanned": result.files_scanned,
        "filesSkipped": result.files_skipped,
        "nodesWritten": counts["nodes"],
        "edgesWritten": counts["edges"],
        "breakdown": by_type,
    }


@app.get("/api/graph")
async def graph() -> dict:
    """Return the full graph in react-force-graph {nodes, links} format."""
    try:
        return await neo4j_client.fetch_graph()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=503, detail=f"Could not read graph: {exc}"
        ) from exc


@app.delete("/api/graph")
async def clear_graph() -> dict:
    """Delete every node and relationship."""
    await neo4j_client.clear_graph()
    return {"status": "cleared"}
