"""Deterministic static scanner engine.

Strategy (deliberately simple + fast for an MVP):
  1. Walk the extracted archive, ignoring vendored / build directories.
  2. Work out the *logical applications* in the tree (one per manifest dir, or
     a single "Main Application" when there is no obvious monorepo).
  3. For each supported source file create a ``Service`` node that hangs off its
     owning ``Application`` via a ``HAS_COMPONENT`` edge.
  4. Apply the regex rules from :mod:`patterns` to emit ``Endpoint``,
     ``ExternalAPI`` and ``Database`` nodes plus their relationship edges.
  5. Resolve local imports in a second pass to connect ``Service`` nodes with
     ``CALLS`` edges.
  6. Roll every service-level DB / third-party connection up to its owning
     ``Application`` so the default (architecture) view is a clean network map.

The scanner is *deterministic*: the same input always yields the same ids and
therefore the same graph. That makes re-scans idempotent in Neo4j.
"""
from __future__ import annotations

import hashlib
import logging
import posixpath
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from ..models import EdgeType, NodeType, ScanResult, ScannedEdge, ScannedNode
from .patterns import (
    DB_PATTERNS,
    ENDPOINT_PATTERNS,
    EXTERNAL_PATTERNS,
    IMPORT_PATTERNS,
    Pattern,
)

logger = logging.getLogger("vectograph.scanner")

# --- file discovery configuration ------------------------------------------
EXTENSION_LANGUAGE = {
    ".js": "js",
    ".jsx": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".ts": "js",
    ".tsx": "js",
    ".py": "py",
}

# Directories that never contain first-party source worth mapping.
IGNORED_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "dist", "build", "out",
    "venv", ".venv", "env", "__pycache__", ".next", ".nuxt", "vendor",
    "coverage", ".pytest_cache", ".mypy_cache", ".tox", "site-packages",
}

# Files that mark the root of a deployable application / microservice. When we
# find more than one of these the codebase is treated as a monorepo and each
# manifest directory becomes its own logical ``Application``.
MANIFEST_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "Pipfile", "go.mod", "pom.xml", "build.gradle",
    "build.gradle.kts", "composer.json", "Gemfile", "Cargo.toml",
}

# Abstraction levels stored on every node so the UI can filter by hierarchy.
LEVEL_ARCHITECTURE = "architecture"
LEVEL_INTERNAL = "internal"

# A single synthetic node representing all inbound traffic to the system.
CLIENT_ID = "client:user"

# Hard limits so a hostile / huge archive cannot hang the process.
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 5_000


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _service_id(rel_path: str) -> str:
    return f"service:{rel_path}"


def _app_id(owner: str) -> str:
    return f"app:{_short_hash(owner or 'root')}"


def _app_name(owner: str, multi: bool) -> str:
    """Human label for an application group.

    A single-application codebase is always "Main Application"; in a monorepo
    each group is named after its directory (the repo root stays "Main
    Application").
    """
    if not owner or not multi:
        return "Main Application"
    return posixpath.basename(owner).replace("-", " ").replace("_", " ").title()


def _manifest_dirs(root: Path) -> set[str]:
    """Relative posix dirs that directly contain an application manifest."""
    dirs: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.name in MANIFEST_FILES:
            dirs.add(posixpath.dirname(path.relative_to(root).as_posix()))
    return dirs


def _owner_dir(rel_path: str, manifest_dirs: set[str]) -> str:
    """Longest manifest directory that is an ancestor of ``rel_path``.

    The deepest match wins so a service-level manifest beats the repo-root one.
    """
    best = ""
    for candidate in manifest_dirs:
        if candidate == "" or rel_path.startswith(candidate + "/"):
            if len(candidate) >= len(best):
                best = candidate
    return best


def _line_context(content: str, index: int) -> tuple[int, str]:
    """Return (1-based line number, trimmed source line) for a match offset."""
    line_no = content.count("\n", 0, index) + 1
    line_start = content.rfind("\n", 0, index) + 1
    line_end = content.find("\n", index)
    if line_end == -1:
        line_end = len(content)
    return line_no, content[line_start:line_end].strip()


def _host_of(url: str) -> str:
    """Best-effort host extraction so one external API maps to one node."""
    try:
        parts = urlsplit(url)
        if parts.netloc:
            return parts.netloc
    except ValueError:
        pass
    return url.split("/")[0] if "/" in url else url


def _dedupe(result: ScanResult) -> ScanResult:
    """Collapse duplicate ids / triples produced by repeated matches."""
    seen_nodes: set[str] = set()
    nodes: list[ScannedNode] = []
    for node in result.nodes:
        if node.id in seen_nodes:
            continue
        seen_nodes.add(node.id)
        nodes.append(node)

    seen_edges: set[tuple[str, str, EdgeType]] = set()
    edges: list[ScannedEdge] = []
    for edge in result.edges:
        key = (edge.source, edge.target, edge.type)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(edge)

    result.nodes = nodes
    result.edges = edges
    return result


class CodeScanner:
    """Scans a directory tree and produces a :class:`ScanResult`."""

    def scan_directory(self, root: Path) -> ScanResult:
        result = ScanResult()

        # --- pass 0: discovery ---------------------------------------------
        files = self._discover_files(root)

        # Maps every known relative path to its Service node id (for CALLS).
        file_index: dict[str, str] = {rel: _service_id(rel) for _, rel, _ in files}

        # --- pass 0.5: logical application grouping ------------------------
        manifest_dirs = _manifest_dirs(root)
        owners = {rel: _owner_dir(rel, manifest_dirs) for _, rel, _ in files}
        owner_dirs = set(owners.values())
        multi = len(owner_dirs) > 1

        app_by_owner = {owner: _app_id(owner) for owner in owner_dirs}
        app_nodes: dict[str, ScannedNode] = {}
        for owner in sorted(owner_dirs):
            app_id = app_by_owner[owner]
            node = ScannedNode(
                id=app_id,
                type=NodeType.APPLICATION,
                name=_app_name(owner, multi),
                file_path=owner,
                level=LEVEL_ARCHITECTURE,
                meta={
                    "directory": owner or ".",
                    "components": 0,
                    "endpoints": 0,
                    "databases": 0,
                    "externalApis": 0,
                },
            )
            app_nodes[app_id] = node
            result.nodes.append(node)

        # Per-application roll-ups of the services they talk to.
        app_db_targets: dict[str, set[str]] = defaultdict(set)
        app_ext_targets: dict[str, set[str]] = defaultdict(set)

        # --- pass 1: per-file detection ------------------------------------
        pending_imports: list[tuple[str, str, str, str]] = []  # (src_id, dir, value, lang)
        for abs_path, rel, language in files:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:  # pragma: no cover - defensive
                logger.warning("Could not read %s: %s", rel, exc)
                result.files_skipped += 1
                continue

            # Cheap binary sniff: NUL bytes indicate a non-text file.
            if "\x00" in content[:1024]:
                result.files_skipped += 1
                continue

            owner = owners[rel]
            app_id = app_by_owner[owner]
            service_id = _service_id(rel)

            # Every source file is a Service, nested under its Application.
            result.nodes.append(
                ScannedNode(
                    id=service_id,
                    type=NodeType.SERVICE,
                    name=posixpath.basename(rel),
                    file_path=rel,
                    parent_id=app_id,
                    level=LEVEL_INTERNAL,
                    meta={
                        "language": language,
                        "directory": posixpath.dirname(rel),
                        "appId": app_id,
                    },
                )
            )
            result.edges.append(
                ScannedEdge(
                    source=app_id, target=service_id, type=EdgeType.HAS_COMPONENT
                )
            )
            app_nodes[app_id].meta["components"] += 1

            nodes, edges, imports = self._scan_file(
                rel, content, language, service_id, app_id
            )
            result.nodes.extend(nodes)
            result.edges.extend(edges)

            for node in nodes:
                if node.type is NodeType.ENDPOINT:
                    app_nodes[app_id].meta["endpoints"] += 1
            for edge in edges:
                if edge.type is EdgeType.QUERIES:
                    app_db_targets[app_id].add(edge.target)
                elif edge.type is EdgeType.REQUESTS:
                    app_ext_targets[app_id].add(edge.target)

            for value in imports:
                pending_imports.append(
                    (service_id, posixpath.dirname(rel), value, language)
                )
            result.files_scanned += 1

        # --- pass 2: resolve imports into CALLS edges ----------------------
        for src_id, cur_dir, value, language in pending_imports:
            target = self._resolve_import(cur_dir, value, language, file_index)
            if target and target != src_id:
                result.edges.append(
                    ScannedEdge(source=src_id, target=target, type=EdgeType.CALLS)
                )

        # --- pass 3: roll services up to their Application -----------------
        for app_id, targets in app_db_targets.items():
            app_nodes[app_id].meta["databases"] = len(targets)
            for target in sorted(targets):
                result.edges.append(
                    ScannedEdge(
                        source=app_id, target=target, type=EdgeType.QUERIES
                    )
                )
        for app_id, targets in app_ext_targets.items():
            app_nodes[app_id].meta["externalApis"] = len(targets)
            for target in sorted(targets):
                result.edges.append(
                    ScannedEdge(
                        source=app_id, target=target, type=EdgeType.REQUESTS
                    )
                )

        # --- pass 4: synthetic client + inbound flows ----------------------
        if app_nodes:
            result.nodes.append(
                ScannedNode(
                    id=CLIENT_ID,
                    type=NodeType.CLIENT,
                    name="Client / User",
                    file_path="",
                    level=LEVEL_ARCHITECTURE,
                    meta={"role": "inbound traffic"},
                )
            )
            for owner in sorted(owner_dirs):
                result.edges.append(
                    ScannedEdge(
                        source=CLIENT_ID,
                        target=app_by_owner[owner],
                        type=EdgeType.USES,
                    )
                )

        return _dedupe(result)

    # -- file discovery ------------------------------------------------------
    def _discover_files(self, root: Path) -> list[tuple[Path, str, str]]:
        """Return ``(abs_path, rel_posix, language)`` for every source file."""
        files: list[tuple[Path, str, str]] = []
        for abs_path in root.rglob("*"):
            if not abs_path.is_file():
                continue
            if any(part in IGNORED_DIRS for part in abs_path.parts):
                continue
            language = EXTENSION_LANGUAGE.get(abs_path.suffix.lower())
            if language is None:
                continue
            if abs_path.stat().st_size > MAX_FILE_BYTES:
                continue
            rel = abs_path.relative_to(root).as_posix()
            files.append((abs_path, rel, language))
            if len(files) >= MAX_FILES:
                logger.warning("Reached MAX_FILES (%d); truncating scan", MAX_FILES)
                break
        return files

    # -- per-file scanning ---------------------------------------------------
    def _scan_file(
        self,
        rel: str,
        content: str,
        language: str,
        service_id: str,
        app_id: str,
    ) -> tuple[list[ScannedNode], list[ScannedEdge], list[str]]:
        nodes: list[ScannedNode] = []
        edges: list[ScannedEdge] = []
        imports: list[str] = []

        for pattern in ENDPOINT_PATTERNS:
            if pattern.language != language:
                continue
            for node in self._match_endpoints(pattern, rel, content, service_id, app_id):
                nodes.append(node)
                edges.append(
                    ScannedEdge(
                        source=service_id, target=node.id, type=EdgeType.EXPOSES
                    )
                )

        for pattern in EXTERNAL_PATTERNS:
            if pattern.language != language:
                continue
            for node in self._match_externals(pattern, rel, content):
                nodes.append(node)
                edges.append(
                    ScannedEdge(
                        source=service_id, target=node.id, type=EdgeType.REQUESTS
                    )
                )

        for pattern in DB_PATTERNS:
            if pattern.language != language:
                continue
            for node in self._match_databases(pattern, rel, content):
                nodes.append(node)
                edges.append(
                    ScannedEdge(
                        source=service_id, target=node.id, type=EdgeType.QUERIES
                    )
                )

        for pattern in IMPORT_PATTERNS:
            if pattern.language != language:
                continue
            for match in pattern.regex.finditer(content):
                value = match.group("value")
                imports.append(value)
                # For `from . import a, b` also try `.a` and `.b` as modules.
                names = match.groupdict().get("names")
                if names:
                    for raw in names.split(","):
                        name = raw.strip().strip("()").split(" as ")[0].strip()
                        if not name or name == "*":
                            continue
                        sep = "" if value.endswith(".") else "."
                        imports.append(f"{value}{sep}{name}")

        return nodes, edges, imports

    # -- per-finding matchers ------------------------------------------------
    def _match_endpoints(
        self, pattern: Pattern, rel: str, content: str, service_id: str, app_id: str
    ) -> list[ScannedNode]:
        out: list[ScannedNode] = []
        for match in pattern.regex.finditer(content):
            path = match.group("value") or "/"
            method = (match.groupdict().get("method") or "GET").upper()
            # Flask encodes the verb inside methods=['GET', ...]
            if method == "ROUTE":
                rest = match.groupdict().get("rest") or ""
                verb = "GET"
                for candidate in ("POST", "PUT", "PATCH", "DELETE", "GET"):
                    if candidate in rest.upper():
                        verb = candidate
                        break
                method = verb

            line, snippet = _line_context(content, match.start())
            node_id = f"endpoint:{_short_hash(f'{rel}:{method}:{path}')}"
            out.append(
                ScannedNode(
                    id=node_id,
                    type=NodeType.ENDPOINT,
                    name=f"{method} {path}",
                    file_path=rel,
                    line=line,
                    snippet=snippet,
                    parent_id=service_id,
                    level=LEVEL_INTERNAL,
                    meta={
                        "method": method,
                        "path": path,
                        "framework": pattern.engine,
                        "appId": app_id,
                    },
                )
            )
        return out

    def _match_externals(
        self, pattern: Pattern, rel: str, content: str
    ) -> list[ScannedNode]:
        out: list[ScannedNode] = []
        for match in pattern.regex.finditer(content):
            url = (match.group("value") or "").strip()
            if not url or url.startswith(("$", "{", "#")):
                continue
            host = _host_of(url)
            method = (match.groupdict().get("method") or "GET").upper()
            line, snippet = _line_context(content, match.start())
            # Deduplicate by host: Stripe stays a single node across the repo.
            node_id = f"external:{_short_hash(host)}"
            out.append(
                ScannedNode(
                    id=node_id,
                    type=NodeType.EXTERNAL_API,
                    name=host,
                    file_path=rel,
                    line=line,
                    snippet=snippet,
                    level=LEVEL_ARCHITECTURE,
                    meta={"url": url, "method": method, "client": pattern.engine},
                )
            )
        return out

    def _match_databases(
        self, pattern: Pattern, rel: str, content: str
    ) -> list[ScannedNode]:
        out: list[ScannedNode] = []
        for match in pattern.regex.finditer(content):
            value = (match.groupdict().get("value") or "").strip()
            # Identifier keeps databases of the same engine distinct per target.
            identifier = value or rel
            line, snippet = _line_context(content, match.start())
            node_id = f"database:{_short_hash(f'{pattern.engine}:{identifier}')}"
            out.append(
                ScannedNode(
                    id=node_id,
                    type=NodeType.DATABASE,
                    name=pattern.engine,
                    file_path=rel,
                    line=line,
                    snippet=snippet,
                    level=LEVEL_ARCHITECTURE,
                    meta={"engine": pattern.engine, "target": value or None},
                )
            )
        return out

    # -- import resolution ---------------------------------------------------
    def _resolve_import(
        self,
        cur_dir: str,
        value: str,
        language: str,
        file_index: dict[str, str],
    ) -> str | None:
        """Map an import specifier to a Service id present in the project."""
        if language == "js":
            return self._resolve_js_import(cur_dir, value, file_index)
        return self._resolve_py_import(cur_dir, value, file_index)

    def _resolve_js_import(
        self, cur_dir: str, value: str, file_index: dict[str, str]
    ) -> str | None:
        base = posixpath.normpath(posixpath.join(cur_dir, value))
        candidates = [
            base,
            *(f"{base}{ext}" for ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")),
            *(
                f"{base}/index{ext}"
                for ext in (".js", ".jsx", ".ts", ".tsx")
            ),
        ]
        for candidate in candidates:
            if candidate in file_index:
                return file_index[candidate]
        return None

    def _resolve_py_import(
        self, cur_dir: str, value: str, file_index: dict[str, str]
    ) -> str | None:
        # Count leading dots: 1 dot = current package, 2 = parent, ...
        dots = len(value) - len(value.lstrip("."))
        module = value[dots:]
        base = cur_dir
        for _ in range(dots - 1):
            base = posixpath.dirname(base)
        rel_module = module.replace(".", "/") if module else ""
        base_path = posixpath.normpath(posixpath.join(base, rel_module)) if rel_module else base
        candidates = [
            f"{base_path}.py",
            f"{base_path}/__init__.py",
            base_path,
        ]
        for candidate in candidates:
            if candidate in file_index:
                return file_index[candidate]
        return None


# Module-level convenience used by the API layer.
scanner = CodeScanner()


def scan_directory(root: Path) -> ScanResult:
    return scanner.scan_directory(root)
