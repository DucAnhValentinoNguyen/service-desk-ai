# Repository Map

This document explains the responsibility of each maintained file in the repository. It focuses on source, configuration, infrastructure, test, and documentation files that matter for development and deployment. Generated folders such as `.git/`, `node_modules/`, `.next/`, and local databases are intentionally excluded.

## Top Level

- `README.md`: Product overview, local startup instructions, demo prompts, and links to the main technical docs.
- `.env.example`: Safe environment-variable template for local development and future cloud adapters.
- `.gitignore`: Excludes local secrets, build output, dependency folders, databases, and transient TypeScript metadata from git.
- `.python-version`: Pins the expected local Python version for `uv` and version managers.
- `pyproject.toml`: Minimal Python package metadata for the repo-level `service-desk-ai` package placeholder.
- `uv.lock`: Lockfile for `uv`; currently captures the repo-level Python environment shape.
- `docker-compose.yml`: Local multi-container entrypoint that wires the API and Next.js frontend together, with host ports `8001` and `3005`.

## CI

- `.github/workflows/ci.yml`: GitHub Actions pipeline for backend install and tests, frontend install and build checks, and gitleaks secret scanning.

## Backend

- `backend/__init__.py`: Marks `backend/` as a Python package.
- `backend/.dockerignore`: Keeps backend container builds small by excluding caches, tests, and local databases from the Docker build context.
- `backend/Dockerfile`: Builds the FastAPI container on Python 3.12 and starts `uvicorn` on port `8000`.
- `backend/requirements.txt`: Backend dependency pin set for FastAPI, Pydantic, Uvicorn, HTTP helpers, and pytest.

## Backend Application

- `backend/app/__init__.py`: Marks `backend/app/` as the importable application package.
- `backend/app/config.py`: Central environment-backed settings object for database path, Kimi/OpenAI provider selection, endpoints/models, reasoning effort, timeout, and CORS origins.
- `backend/app/main.py`: FastAPI entrypoint; defines login, database-backed identity context, server-side role/ownership authorization, approval execution, and request orchestration.
- `backend/app/schemas.py`: Pydantic request and response contracts shared across the API, the RAG flow, calls, approvals, and ticket transitions.
- `backend/app/store.py`: SQLite persistence layer; owns schema creation/migrations, demo identities and password hashes, request ownership, tickets, proposals, approvals, audit trails, documents, and appointments.
- `backend/app/rag.py`: Local RAG implementation; handles document chunking, lightweight indexing, permission-aware retrieval, prompt-injection detection, citation shaping, and abstention behavior.
- `backend/app/knowledge/`: Versioned Markdown demo corpus. Each file contains front matter for its database ID, access sensitivity, product area, allowed models, and optional source URL. The body is synthetic demo policy text.
- `backend/app/agents.py`: Front-door AI router plus bounded specialist orchestration for supply chain, CRM, HR, and appointment flows; trusted code validates every model decision.
- `backend/app/guardrails.py`: Central safety checks for abuse and prompt injection, approval gating, approver-role checks, and simple HR redaction.
- `backend/app/adapters.py`: Contract-faithful simulator adapters for ERP, CRM, HRM, ticketing, and calendar tool surfaces.
- `backend/app/ports.py`: Deployment seam definitions for object storage, queues, and identity, plus local development implementations.
- `backend/app/providers.py`: Model-provider abstraction layer with a no-network demo fallback and shared OpenAI-compatible adapters for Kimi K3 and OpenAI routing, grounded answers, and specialist drafts.
- `backend/app/jobs.py`: Local durable job runner abstraction with retries and dead-letter status for future background workflows.

## Knowledge Corpus

- `backend/app/knowledge/supply-chain-policy.md`: Synthetic ERP inventory and late purchase-order policy, with a public building-automation context link.
- `backend/app/knowledge/room-sensor-support.md`: Synthetic CRM troubleshooting playbook for missing room-sensor readings, with an optional public product-page link.
- `backend/app/knowledge/employee-leave-policy.md`: Restricted synthetic HR leave policy.
- `backend/app/knowledge/technician-appointment-policy.md`: Synthetic calendar booking policy, with an optional public application-notes link.
- `backend/app/knowledge/escalation-policy.md`: Public synthetic policy describing when to abstain or escalate.

## Frontend

- `frontend/.dockerignore`: Excludes local Next.js artifacts and dependency folders from frontend container builds.
- `frontend/Dockerfile`: Builds the development container for the Next.js console and exposes port `3005`.
- `frontend/package.json`: Frontend scripts and dependency manifest for the service-desk console.
- `frontend/package-lock.json`: Exact npm dependency lockfile for reproducible frontend installs in local runs and CI.
- `frontend/next.config.mjs`: Small Next.js configuration file; disables the `X-Powered-By` header.
- `frontend/tsconfig.json`: TypeScript compiler configuration for the app router frontend.
- `frontend/next-env.d.ts`: Standard Next.js type shim that wires framework-generated types into TypeScript.
- `frontend/app/layout.tsx`: Global HTML shell and page metadata for the frontend app router.
- `frontend/app/page.tsx`: Main single-page demo console; renders login, role-scoped Inbox, combined knowledge query, request detail, and owner-only approval actions.
- `frontend/app/globals.css`: Global design system and responsive styling for the dashboard UI.

## Infrastructure

- `infra/postgres-init.sql`: Starter SQL for a production PostgreSQL bootstrap, including the `pgvector` extension marker and schema metadata.
- `infra/terraform/main.tf`: First-pass AWS Terraform scaffold for an artifact bucket and job queues in `eu-north-1`.

## Tests

- `tests/__init__.py`: Marks the test directory as a package.
- `tests/test_app.py`: Integration-style API tests covering routing, escalation, approval authorization, RAG citations, and idempotent calendar booking.

## Docs

- `docs/ARCHITECTURE.md`: High-level system architecture, trust boundaries, and demo walkthrough order.
- `docs/API.md`: Example HTTP requests for the most important user journeys.
- `docs/DEMO_GUIDE.md`: Repeatable role-by-role demo sequence and expected outcomes.
- `docs/PRESENTATION.md`: Timed ten-minute presentation narrative.
- `docs/REPOSITORY_MAP.md`: This file; a file-by-file responsibility guide for the repository.

## Repo-Level Package

- `src/service_desk_ai/__init__.py`: Placeholder package entrypoint from the repo bootstrap. It is not part of the FastAPI runtime and can later become a shared CLI or be removed if the backend remains the only Python runtime surface.
