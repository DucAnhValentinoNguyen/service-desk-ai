# API Examples

The interactive OpenAPI contract is available at `/docs`.

## Create and triage a request

```http
POST /v1/requests
X-Demo-User: demo-admin
Content-Type: application/json

{"content":"Inventory for gateway batteries is below the reorder point and the supplier PO is late.","source":"web"}
```

The response contains the canonical ticket, classification, evidence citations, and an approval-backed proposal when a protected mutation is suggested.

## Ask the knowledge base

```http
POST /v1/knowledge/query
Content-Type: application/json

{"question":"What is the reorder point for gateway batteries?"}
```

Grounded answers contain citations. Low-evidence and prompt-injection requests return an explicit safe refusal.

## Approve a protected action

```http
POST /v1/approvals/{approval_id}/approve
X-Demo-User: demo-admin
Content-Type: application/json

{"note":"Reviewed by operations owner"}
```

Only `owner` and `admin` demo roles can approve. The simulator write receives an idempotency key and the execution is appended to the ticket audit timeline.
