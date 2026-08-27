# Ten-Minute Presentation Script

## 0:00-1:00 - The problem

Operations teams receive customer issues, HR requests, supply-chain exceptions, and appointment needs through disconnected channels. The usual failure mode is not a lack of AI; it is untracked work, unclear ownership, and unsafe automation. Service Desk AI turns each request into a visible, controlled workflow.

## 1:00-2:30 - What the product does

The user signs in, writes naturally in a single Inbox, and chooses either **Ask knowledge** or **Submit request**. The intake agent classifies the request, selects exactly one bounded specialist, retrieves approved policy evidence, creates a ticket, and proposes the next action. It supports ERP supply-chain exceptions, CRM device support, HR requests, and technician appointments.

## 2:30-4:00 - Safety and access

Show the login page. Explain the hierarchy: Duc-Anh is the IT administrator and has global visibility plus approval rights. Giulia is an HR specialist. Alex is a CRM and ERP specialist. Tim is a staff member and John is a customer. Tim and John only see their own requests. This is not just a visual restriction: request ownership is stored in SQLite and enforced by the FastAPI API on every list and detail request.

## 4:00-5:30 - AI and RAG

Sign in as Alex and ask: `What should an operator check when a purchase order is late?` Click **Ask knowledge**. Point out the cited answer. The RAG pipeline normalizes seeded documents, chunks them by paragraph/section, applies role-aware retrieval, rejects prompt injection, and returns a grounded answer or abstains. With `OPENAI_API_KEY` configured, OpenAI writes the route, grounded answer, and specialist draft; trusted Python validates every structured result.

## 5:30-7:30 - End-to-end workflow

Submit the room-sensor support request. Show that the CRM specialist is selected, a ticket is created, the customer response is drafted, and no message has been sent yet. Sign in as Duc-Anh, open Approvals, and inspect the proposal payload. Approve it. Explain that approval triggers the simulator write with an idempotency key, adds the audit event, marks the proposal executed, and resolves the ticket. Rejecting would create the same audit trail but make no external write.

## 7:30-8:45 - Guardrails

Submit a prompt-injection request. It reaches human review and cannot create any proposal. The safety model is layered: authenticated identity, workspace ownership, role visibility, specialist tool allowlists, Pydantic schemas, prompt-injection checks, approval gates, idempotency, and an append-only audit trail.

## 8:45-10:00 - Technology and value

The frontend is Next.js 14 with TypeScript; the backend is FastAPI with Pydantic contracts. Local persistence is SQLite in a Docker volume, shaped so it can move to PostgreSQL with pgvector. Docker Compose runs the whole application locally. The provider layer supports OpenAI and safe deterministic fallback. The deployment seams cover AWS Cognito, S3, SQS, ECS/Fargate, RDS, CloudWatch, and Secrets Manager. For a customer, this means faster handling without letting AI silently modify their ERP, CRM, or HR systems. The platform starts as a demonstrable, safe workflow and can replace each simulator with a production connector when ready.
