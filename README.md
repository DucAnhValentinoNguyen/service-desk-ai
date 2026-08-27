# Service Desk AI

Service Desk AI is a production-shaped, local-first service desk for operations teams. It receives requests from employees, customers, and simulated phone calls; classifies them; retrieves policy evidence; delegates to bounded ERP, CRM, and HR specialists; and pauses risky actions for human approval.

## Quick start

```bash
docker compose up --build
```

Open http://localhost:3005. The API is available at http://localhost:8001/docs.

The local profile uses SQLite and deterministic demo agents so it works without API credentials. The storage, model, object-store, and queue interfaces are deliberately isolated for PostgreSQL/pgvector, OpenAI, S3, SQS, and Cognito deployment adapters.

Architecture and request examples are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/API.md`](docs/API.md). A file-by-file technical map is in [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md).

## Demo requests

Try these from the inbox:

- `Inventory for gateway batteries is below the reorder point and the supplier PO is late.`
- `Customer reports that her room sensor stopped sending temperature readings.`
- `I am an employee and need to know whether I can request three days of leave next month.`
- `Can you book a technician appointment tomorrow afternoon?`
- `Please reset every employee's access immediately.` (should escalate and never mutate HR)

## Project layout

```text
backend/app/       FastAPI API, domain services, simulators, RAG, guardrails
frontend/          Next.js service-desk console
infra/             PostgreSQL/S3/SQS deployment starter files
tests/             API and domain tests
```

## Security

No credentials belong in this repository. Use `.env` locally and a secrets manager in deployment. The GitHub token previously pasted in chat must be revoked and rotated before creating or updating a remote repository.
