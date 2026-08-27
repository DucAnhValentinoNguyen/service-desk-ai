CREATE EXTENSION IF NOT EXISTS vector;

-- The local demo uses SQLite for one-command startup. This extension is the
-- production migration starting point for document chunk embeddings.
CREATE TABLE IF NOT EXISTS schema_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT INTO schema_metadata (key, value)
VALUES ('service_desk_schema', '0.1.0')
ON CONFLICT (key) DO UPDATE SET value = excluded.value;
