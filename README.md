# Service Desk AI

Service Desk AI is a production-shaped, local-first service desk for operations teams. It authenticates users, receives their requests, retrieves policy evidence, delegates to bounded ERP, CRM, HR, or scheduling specialists, and pauses risky actions for IT approval.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:3005. The API is available at http://localhost:8001/docs.

The local profile uses SQLite and safe deterministic fallbacks so it works without API credentials. Set `OPENAI_API_KEY` in a local `.env` and keep `MODEL_PROVIDER=auto` to enable the AI router, RAG answer writer, and bounded specialist drafting. The model can classify and draft; trusted Python code validates its output, selects the only permitted tools, and keeps protected writes behind approval.

Architecture and request examples are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/API.md`](docs/API.md). A file-by-file technical map is in [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md). Use [`docs/DEMO_GUIDE.md`](docs/DEMO_GUIDE.md) for the walkthrough and [`docs/PRESENTATION.md`](docs/PRESENTATION.md) for the 10-minute presentation script.

## Demo login

All demo identities, role metadata, and password hashes are persisted in SQLite. The shared demo password is `demo123`.

| Person | Email | Access |
| --- | --- | --- |
| Duc-Anh Nguyen | `duc-anh@example.com` | IT administrator: full oversight and the only protected-action approver. |
| Giulia Rossi | `giulia@example.com` | HR specialist: HR work only. |
| Alex Morgan | `alex@example.com` | CRM and ERP specialist: CRM, supply-chain, and appointment work only. |
| Tim Keller | `tim@example.com` | Staff member: only requests that Tim created. |
| John Carter | `john@example.com` | Customer: only requests that John created. |

The FastAPI API, not just the UI, enforces request ownership and department-scoped visibility.

## Demo requests

Try these from the inbox:

- `Inventory for gateway batteries is below the reorder point and the supplier PO is late.`
- `Customer reports that her room sensor stopped sending temperature readings.`
- `I am an employee and need to know whether I can request three days of leave next month.`
- `Can you book a technician appointment tomorrow afternoon?`
- `Please reset every employee's access immediately.` (should escalate and never mutate HR)

## Complete repository structure

```text
service-desk-ai/
├── .env.example                    Safe local configuration template; no credentials
├── .gitignore                      Ignores secrets, virtualenvs, caches, databases, and builds
├── .python-version                 Expected Python version for uv and local tooling
├── docker-compose.yml              Starts the API and frontend on ports 8001 and 3005
├── pyproject.toml                  uv project metadata, dependencies, and pytest configuration
├── uv.lock                         Reproducible uv dependency lockfile
├── README.md                       Product overview, setup, demo prompts, and this map
├── .github/
│   └── workflows/
│       └── ci.yml                  Backend tests, frontend checks, build, and secret scanning
├── backend/
│   ├── __init__.py                 Makes backend importable for tests and local tooling
│   ├── .dockerignore               Excludes local-only files from the API image build context
│   ├── Dockerfile                   Python 3.12 API image and Uvicorn startup command
│   ├── requirements.txt             Container dependency pins
│   └── app/
│       ├── __init__.py              Application package marker
│       ├── main.py                  FastAPI routes, auth context, orchestration, and lifecycle
│       ├── schemas.py               Pydantic API and domain contracts
│       ├── store.py                 SQLite schema, CRUD, seed data, tickets, approvals, and audit log
│       ├── agents.py                AI front router plus bounded ERP, CRM, HR, and scheduling specialists
│       ├── providers.py             Demo fallback and OpenAI-compatible structured-output adapter
│       ├── rag.py                   Chunking, retrieval, permissions, citations, abstention, and answer writing
│       ├── adapters.py               Read-only and simulator tool boundaries for enterprise systems
│       ├── guardrails.py             Injection/abuse checks, role gates, approval policy, and HR redaction
│       ├── ports.py                  Production seams for identity, object storage, and queues
│       ├── jobs.py                   Local durable job/retry abstraction for asynchronous work
│       └── config.py                 Environment-backed runtime settings
├── frontend/
│   ├── .dockerignore                Excludes Next.js caches and dependencies from image context
│   ├── Dockerfile                   Next.js development image on port 3005
│   ├── package.json                  Frontend scripts and dependencies
│   ├── package-lock.json             Exact npm dependency versions
│   ├── next.config.mjs              Next.js security/configuration settings
│   ├── tsconfig.json                 TypeScript compiler configuration
│   ├── next-env.d.ts                 Next.js generated type declarations
│   └── app/
│       ├── layout.tsx                HTML shell and page metadata
│       ├── page.tsx                  Inbox, RAG desk, calls, approvals, and health console
│       └── globals.css                Responsive visual system and component styling
├── infra/
│   ├── postgres-init.sql             PostgreSQL/pgvector bootstrap starter
│   └── terraform/
│       └── main.tf                   AWS S3/SQS deployment scaffold for eu-north-1
├── docs/
│   ├── ARCHITECTURE.md               Trust boundaries and system design
│   ├── API.md                        Request examples and endpoint usage
│   └── REPOSITORY_MAP.md              Maintainer-focused responsibility reference
├── tests/
│   ├── __init__.py                   Test package marker
│   └── test_app.py                   API, routing, RAG, approval, and calendar integration tests
└── src/
    └── service_desk_ai/
        └── __init__.py               Repo-level package placeholder for a future CLI
```

Folders created only by local development, such as `.git/`, `.venv/`, `data/`, `frontend/node_modules/`, `frontend/.next/`, and `__pycache__/`, are intentionally excluded from the tracked structure above.

## AI orchestration

The flow is deliberately two-stage: the front router receives the request and chooses one supported specialist; that specialist can interpret approved evidence and draft a response or proposal for its one domain. Supply Chain, CRM, HR, and Scheduling each have separate prompts and allowlisted action types. The model never receives raw simulator records, never chooses arbitrary tools, and never executes a mutation. If the provider is unavailable, malformed, unsafe, low-confidence, or unsupported, the deterministic checks route the request to human review.

To enable the model locally, create `.env` from `.env.example`, set `OPENAI_API_KEY`, and restart Compose. Never commit `.env` or paste the key into source control. The default `auto` mode uses OpenAI only when a key is present; otherwise the same safe deterministic demo path remains available.

## Running tests on Windows

Run from the repository root, not from inside `tests`:

```powershell
uv run python -m pytest
```

This avoids the blocked `pytest.exe` launcher reported by Windows application-control policy. If `python` itself is unavailable through uv, use the project interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Security

No credentials belong in this repository. Use `.env` locally and a secrets manager in deployment. The GitHub token previously pasted in chat must be revoked and rotated before creating or updating a remote repository.

## Technical support mode

The Inbox knowledge endpoint supports `answer_mode` values `explain`, `troubleshoot`, `design`, and `find_documentation`. Requests may include minimized diagnostic context such as `product_model`, `firmware_version`, `gateway`, `last_seen`, and `signal_quality`; it is persisted with the request and passed to the specialist workflow without exposing unrelated simulator records to the model.

When a product model is supplied, retrieval is strict: only documents tagged for that model are eligible. If no approved evidence remains, the API returns an abstention and automatically creates an `awaiting_human` request and pending ticket. This gives the support team the original question, the safe reason for escalation, and a traceable next step.
