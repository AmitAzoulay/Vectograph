# Vectograph

**Cybersecurity Architecture Mapping Tool for Pentesters.**

Upload a compressed codebase (`.zip`), and Vectograph statically scans it to
build a two-level architecture map — a high-level network view of the
**Application**, **Client / User**, **Databases** and **External APIs**, with
every internal file and HTTP route available as a **drill-down** into an
application. The graph is stored in Neo4j and rendered as a highly interactive,
physics-based map.

> **Zero dependencies:** the only thing you need installed is Docker.

---

## Architecture

```
┌──────────────┐   HTTP    ┌──────────────┐   Bolt   ┌──────────────┐
│  frontend    │ ────────▶ │   backend    │ ───────▶ │    neo4j     │
│ React + Vite │  /api/*   │   FastAPI    │  driver  │  graph store │
└──────────────┘           └──────────────┘          └──────────────┘
```

| Service    | Tech                                   | Port  |
| ---------- | -------------------------------------- | ----- |
| `neo4j`    | Neo4j 5.20 Community                   | 7474 / 7687 |
| `backend`  | Python 3.11 · FastAPI · neo4j driver   | 8000  |
| `frontend` | React 18 · Vite · Tailwind · force-graph | 5173 |

## Quick start

```bash
git clone <this-repo> vectograph && cd vectograph
docker compose up --build
```

Then open **http://localhost:5173**, drop in a `.zip` of JS/TS/Python code and
watch the graph build itself.

- Neo4j Browser: http://localhost:7474 (user `neo4j` / password `vectograph`)
- API docs: http://localhost:8000/docs

Optional: copy `.env.example` to `.env` to change credentials or ports.

## How the scanner works

`backend/app/scanner/` is a **deterministic** static analyser (regex rule set,
no execution of untrusted code):

| Detects | Example idioms | Node |
| ------- | -------------- | ---- |
| Application roots | `package.json`, `requirements.txt`, `pyproject.toml`, … | `Application` |
| HTTP routes | `app.get('/x')`, `@router.post("/y")`, `@app.route` | `Endpoint` |
| External calls | `axios.get()`, `fetch()`, `requests.post()`, `httpx.get()` | `ExternalAPI` |
| DB connections | `mongoose.connect()`, `psycopg2.connect()`, `create_engine()`, `redis.createClient()` | `Database` |
| Local imports | `import ./x`, `from .mod import` | `Service → Service` |

Rules live declaratively in `scanner/patterns.py` — add a framework by adding a
pattern.

### Abstraction levels

The scanner never puts a file directly on the top-level map. Instead it groups
the codebase into one logical **`Application`** per manifest directory (a
single "Main Application" when there is no obvious monorepo), then:

- every source file becomes a `Service` **child** of its application
  (`HAS_COMPONENT` edge);
- every route becomes an `Endpoint` child of its file (`EXPOSES` edge);
- each application's database / third-party connections are rolled up into
  top-level `Application → Database` (`QUERIES`) and
  `Application → ExternalAPI` (`REQUESTS`) flows.

### Graph model (Neo4j)

- **Architecture (top-level) nodes:** `Application`, `Client`, `Database`,
  `ExternalAPI` (`level = "architecture"`)
- **Internal (child) nodes:** `Service`, `Endpoint` (`level = "internal"`,
  each tagged with a `parentId`)
- **Relationships:** `HAS_COMPONENT`, `USES`, `CALLS`, `EXPOSES`, `QUERIES`,
  `REQUESTS`

Every node carries `id`, `name`, `type`, `level`, `parentId`, `filePath`,
`line`, `snippet` and a JSON `meta` blob. Every upload replaces the previous
graph (MVP semantics).

## API

| Method | Path          | Description                                  |
| ------ | ------------- | -------------------------------------------- |
| `POST` | `/api/upload` | Upload a `.zip`; scan + persist the graph    |
| `GET`  | `/api/graph`  | Full hierarchical graph as `{ nodes, links, applications }` |
| `DELETE` | `/api/graph` | Wipe the graph                              |
| `GET`  | `/api/health` | Backend + Neo4j health                       |

## UI features

- Sleek drag & drop upload with an "Analyzing Architecture…" spinner.
- Full-screen physics graph (drag, pan, zoom).
- Two viewing states: the default **Architecture** network map, and an
  **Internal** component view per application.
- **Drill-down:** double-click an `Application` node — or use the *Drill into
  components* button in the side drawer — to reveal its files, routes and
  outbound calls. A breadcrumb / *Back to Architecture* button returns you up.
- Colour-coded nodes: Applications cyan, Clients purple, Endpoints green,
  Databases blue, External APIs red, Services gray.
- Hover a node → highlight its connections, dim the rest.
- Click a node → side drawer with type, file path, line and the exact code
  snippet that created it.

## Project layout

```
.
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # FastAPI routes
│       ├── config.py          # env-driven settings
│       ├── neo4j_client.py    # driver + Cypher read/write
│       ├── archive.py         # safe zip extraction
│       ├── models.py          # node/edge domain model
│       └── scanner/
│           ├── patterns.py    # detection rule set
│           └── engine.py      # scan + import resolution
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── App.jsx
        ├── api.js
        ├── graph/config.js    # colours, physics, helpers
        └── components/
            ├── UploadView.jsx
            ├── GraphView.jsx
            ├── NodeDrawer.jsx
            └── Legend.jsx
```

## Security notes

- Uploaded archives are extracted with zip-slip and decompression-bomb guards.
- Code is **never executed** — analysis is purely textual.
- `node_modules`, build output and version control dirs are skipped.

## Roadmap

- Language-aware AST parsing (tree-sitter) for higher-fidelity call graphs.
- AI-assisted classification of components and risk scoring.
- Multi-project workspaces and diffing between scans.
