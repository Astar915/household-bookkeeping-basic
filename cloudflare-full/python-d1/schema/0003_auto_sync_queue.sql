CREATE TABLE IF NOT EXISTS auto_sync_queue (
    user_id TEXT PRIMARY KEY REFERENCES cloud_users(id) ON DELETE CASCADE,
    revision TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'queued', 'done', 'failed')),
    operation_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auto_sync_queue_work
    ON auto_sync_queue(state, updated_at, user_id);

CREATE TABLE IF NOT EXISTS worker_maintenance_state (
    state_key TEXT PRIMARY KEY,
    state_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
