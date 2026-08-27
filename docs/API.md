# API Examples

The interactive OpenAPI contract is available at `/docs`.

## Create and triage a request

```http
POST /v1/requests
X-Demo-User: alex-ops
Content-Type: application/json

{"content":"Inventory for gateway batteries is below the reorder point and the supplier PO is late.","source":"web"}
```

The response contains the canonical ticket, classification, evidence citations, and an approval-backed proposal when a protected mutation is suggested.

## Ask the knowledge base

```http
POST /v1/knowledge/query
Content-Type: application/json

{"question":"How should I troubleshoot a room sensor?","answer_mode":"troubleshoot","product_model":"room-sensor","firmware_version":"2.4"}
```

Grounded answers contain citations, and can be requested in `explain`, `troubleshoot`, `design`, or `find_documentation` mode. `product_model` and `firmware_version` narrow retrieval context. Low-evidence and prompt-injection requests return an explicit safe refusal and create an `awaiting_human` request/ticket for follow-up.

## Approve a protected action

```http
POST /v1/approvals/{approval_id}/approve
X-Demo-User: duc-anh
Content-Type: application/json

{"note":"Reviewed by operations owner"}
```

Only the `owner` IT administrator can approve. The simulator write receives an idempotency key, the proposal is marked executed, and the execution is appended to the ticket audit timeline.
