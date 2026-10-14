"""The deterministic "knowledge base" of the static scanner.

Every entry is a regular expression that matches a well-known framework idiom
plus a small amount of metadata telling the engine what it found. This keeps
the detection logic declarative: to support a new framework you usually only
add a pattern here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Finding(Enum):
    ENDPOINT = "endpoint"
    EXTERNAL = "external"
    DATABASE = "database"
    IMPORT = "import"


@dataclass(frozen=True, slots=True)
class Pattern:
    """A compiled detection rule.

    Attributes:
        finding:  what kind of entity this rule produces.
        regex:    compiled expression. Must contain named groups:
                  ``value`` (the interesting string) and optionally ``method``.
        engine:   human readable label, e.g. "Express", "MongoDB".
        language: "js" or "py" (used to filter which files are examined).
    """

    finding: Finding
    regex: re.Pattern[str]
    engine: str
    language: str


def _p(finding: Finding, regex: str, engine: str, language: str) -> Pattern:
    # re.MULTILINE so ^/$ based rules still work but more importantly so `.`
    # behaves predictably on multi-line files. re.IGNORECASE because framework
    # usage is frequently written in mixed case.
    return Pattern(finding, re.compile(regex, re.MULTILINE), engine, language)


# ---------------------------------------------------------------------------
# HTTP endpoint definitions  ->  Endpoint nodes
# ---------------------------------------------------------------------------
ENDPOINT_PATTERNS: list[Pattern] = [
    # Express / Koa / Fastify style: app.get('/x'), router.post("/y"), etc.
    _p(
        Finding.ENDPOINT,
        r"\b(?:app|router|server|api|fastify)\s*\.\s*"
        r"(?P<method>get|post|put|patch|delete|options|head|all|use)\s*\(\s*"
        r"['\"`](?P<value>[^'\"`]+)['\"`]",
        "Express",
        "js",
    ),
    # NestJS style decorators: @Get('/x'), @Post('/y')
    _p(
        Finding.ENDPOINT,
        r"@(?P<method>Get|Post|Put|Patch|Delete|Options|Head|All)\s*\(\s*"
        r"['\"`](?P<value>[^'\"`]*)['\"`]",
        "NestJS",
        "js",
    ),
    # Flask: @app.route('/x', methods=['GET'])
    _p(
        Finding.ENDPOINT,
        r"@\s*\w+\s*\.\s*route\s*\(\s*['\"](?P<value>[^'\"]+)['\"]"
        r"(?P<rest>[^)]*)\)",
        "Flask",
        "py",
    ),
    # FastAPI: @app.get('/x'), @router.post("/y")
    _p(
        Finding.ENDPOINT,
        r"@\s*\w+\s*\.\s*(?P<method>get|post|put|patch|delete|head|options)\s*"
        r"\(\s*['\"](?P<value>[^'\"]+)['\"]",
        "FastAPI",
        "py",
    ),
]

# ---------------------------------------------------------------------------
# Third party API calls  ->  ExternalAPI nodes
# ---------------------------------------------------------------------------
EXTERNAL_PATTERNS: list[Pattern] = [
    # axios.get('https://api.stripe.com/...')
    _p(
        Finding.EXTERNAL,
        r"\baxios\s*\.\s*(?P<method>get|post|put|patch|delete|head|options)\s*"
        r"\(\s*['\"`](?P<value>[^'\"`]+)['\"`]",
        "axios",
        "js",
    ),
    # axios({ url: 'https://...' })
    _p(
        Finding.EXTERNAL,
        r"\baxios\s*\(\s*\{[^}]*?url\s*:\s*['\"`](?P<value>[^'\"`]+)['\"`]",
        "axios",
        "js",
    ),
    # fetch('https://...')
    _p(
        Finding.EXTERNAL,
        r"\bfetch\s*\(\s*['\"`](?P<value>[^'\"`]+)['\"`]",
        "fetch",
        "js",
    ),
    # Python: requests.post('https://...'), httpx.get(...)
    _p(
        Finding.EXTERNAL,
        r"\b(?:requests|httpx)\s*\.\s*"
        r"(?P<method>get|post|put|patch|delete|head|options)\s*"
        r"\(\s*(?:f?['\"])(?P<value>[^'\"]+)['\"]",
        "requests",
        "py",
    ),
    # Python: urllib.request.urlopen('https://...')
    _p(
        Finding.EXTERNAL,
        r"\burlopen\s*\(\s*(?:f?['\"])(?P<value>[^'\"]+)['\"]",
        "urllib",
        "py",
    ),
]

# ---------------------------------------------------------------------------
# Database connections  ->  Database nodes
# ---------------------------------------------------------------------------
DB_PATTERNS: list[Pattern] = [
    _p(
        Finding.DATABASE,
        r"\bmongoose\s*\.\s*connect\s*\(\s*['\"`](?P<value>[^'\"`]+)['\"`]",
        "MongoDB",
        "js",
    ),
    _p(
        Finding.DATABASE,
        r"\bMongoClient\s*\(\s*(?:['\"`](?P<value>[^'\"`]+)['\"`])?",
        "MongoDB",
        "py",
    ),
    _p(
        Finding.DATABASE,
        r"\bpsycopg2\s*\.\s*connect\s*\((?P<value>[^)]*)\)",
        "PostgreSQL",
        "py",
    ),
    _p(
        Finding.DATABASE,
        r"\bcreate_engine\s*\(\s*['\"](?P<value>[^'\"]+)['\"]",
        "SQLAlchemy",
        "py",
    ),
    _p(
        Finding.DATABASE,
        r"\bredis\s*\.\s*(?:createClient|Redis)\s*\(",
        "Redis",
        "js",
    ),
    _p(
        Finding.DATABASE,
        r"\bredis\s*\.\s*Redis\s*\(\s*(?:host\s*=\s*['\"](?P<value>[^'\"]+)['\"])?",
        "Redis",
        "py",
    ),
    _p(
        Finding.DATABASE,
        r"\bnew\s+(?:pg\.)?Pool\s*\(",
        "PostgreSQL",
        "js",
    ),
    _p(
        Finding.DATABASE,
        r"\b(?:mysql\s*\.\s*)?createConnection\s*\(",
        "MySQL",
        "js",
    ),
    _p(
        Finding.DATABASE,
        r"\bnew\s+Sequelize\s*\((?P<value>[^)]*)\)",
        "Sequelize",
        "js",
    ),
    _p(
        Finding.DATABASE,
        r"\bknex\s*\(\s*(?P<value>[^)]*)\)",
        "Knex",
        "js",
    ),
]

# ---------------------------------------------------------------------------
# Local imports  ->  CALLS edges between Service nodes
# ---------------------------------------------------------------------------
IMPORT_PATTERNS: list[Pattern] = [
    # import x from './y'   |   require('./y')
    _p(
        Finding.IMPORT,
        r"(?:\bimport\b[^;'\"]*?from\s*|\brequire\s*\(\s*)"
        r"['\"](?P<value>\.{1,2}/[^'\"]+)['\"]",
        "es-module",
        "js",
    ),
    # from .module import thing  |  from ..pkg.mod import thing
    # The `names` group lets the engine also try each imported name as a
    # submodule (covers the common `from . import service` idiom).
    _p(
        Finding.IMPORT,
        r"^\s*from\s+(?P<value>\.+[\w.]*)\s+import\s+(?P<names>.+)$",
        "python-relative",
        "py",
    ),
    # import .module (rare but valid)
    _p(
        Finding.IMPORT,
        r"^\s*import\s+(?P<value>\.+[\w.]*)\s*$",
        "python-relative",
        "py",
    ),
]


# All pattern groups keyed for convenient iteration in the engine.
ALL_PATTERNS: dict[Finding, list[Pattern]] = {
    Finding.ENDPOINT: ENDPOINT_PATTERNS,
    Finding.EXTERNAL: EXTERNAL_PATTERNS,
    Finding.DATABASE: DB_PATTERNS,
    Finding.IMPORT: IMPORT_PATTERNS,
}


def patterns_for(findings: tuple[Finding, ...]) -> list[Pattern]:
    """Return every pattern matching any of the requested findings."""
    out: list[Pattern] = []
    for finding in findings:
        out.extend(ALL_PATTERNS[finding])
    return out
