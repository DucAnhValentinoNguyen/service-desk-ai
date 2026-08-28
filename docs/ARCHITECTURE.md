# Service Desk AI Architecture

The service is intentionally split into trusted orchestration and untrusted model-facing components.

```text
authenticated web inbox
        |
        v
FastAPI intake -> guardrails -> deterministic router -> bounded specialist
        |                                      |
        v                                      v
canonical ticket + audit trail       RAG evidence + typed simulator reads
        |
        v
proposal -> approval policy -> simulator write -> timeline
```

The demo uses SQLite, a local object store, and an in-process retry runner. The contracts in `backend/app/ports.py` are the replacement seams for PostgreSQL/pgvector, S3, SQS/DLQ, and Cognito. The provider adapter defaults to Kimi K3, supports OpenAI as an alternative, and can target any compatible self-hosted endpoint. No model response is treated as authorization to write to an external system.

## Trust boundaries

- User and document text is untrusted input.
- RAG citations are evidence, not instructions.
- Specialist agents only receive typed, allowlisted tools.
- ERP, CRM, HRM, and calendar writes pass through proposals and approval policy.
- Audit events are append-only application records for every mutation.

## Demo walkthrough

1. Submit the late purchase-order prompt and show the ERP proposal in the Inbox request detail.
2. Submit the sensor-support prompt and show the CRM response proposal in the Inbox.
3. Submit the leave-policy prompt and show HR evidence plus approval gating.
4. Use the Inbox knowledge action for a cited policy answer and an unsupported question.
5. Submit an appointment request and show its protected scheduling proposal.
6. Submit the prompt-injection or mass-access prompt and show human escalation.
