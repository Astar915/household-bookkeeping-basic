PRAGMA foreign_keys = ON;

-- Authentication lives in D1 rather than in an ephemeral Worker filesystem.
CREATE TABLE IF NOT EXISTS cloud_users (
    id TEXT PRIMARY KEY,
    github_login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    github_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cloud_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    csrf_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_sessions_user ON cloud_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_cloud_sessions_expiry ON cloud_sessions(expires_at);

CREATE TABLE IF NOT EXISTS github_login_flows (
    flow_id TEXT PRIMARY KEY,
    cookie_hash TEXT NOT NULL,
    device_code TEXT NOT NULL,
    user_code TEXT NOT NULL,
    verification_uri TEXT NOT NULL,
    poll_interval_seconds INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    last_polled_at TEXT,
    state TEXT NOT NULL DEFAULT 'pending',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_login_flows_cookie ON github_login_flows(cookie_hash);
CREATE INDEX IF NOT EXISTS idx_github_login_flows_expiry ON github_login_flows(expires_at);

-- One manifest is the commit point for a user's full app state. File chunks are
-- staged first and become visible together only when this revision advances.
CREATE TABLE IF NOT EXISTS user_state_roots (
    user_id TEXT PRIMARY KEY REFERENCES cloud_users(id) ON DELETE CASCADE,
    revision TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_state_chunks (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_revision TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    payload_base64 TEXT NOT NULL,
    PRIMARY KEY (user_id, file_path, file_revision, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_user_state_chunks_current
    ON user_state_chunks(user_id, file_path, file_revision, chunk_index);

-- Durable job envelopes and Agent conversation state replace isolate-local
-- dictionaries/background threads while keeping the existing mobile API shape.
CREATE TABLE IF NOT EXISTS app_jobs (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    operation_id TEXT NOT NULL,
    action TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, operation_id)
);
CREATE INDEX IF NOT EXISTS idx_app_jobs_state ON app_jobs(user_id, state, updated_at);


CREATE TABLE IF NOT EXISTS agent_conversations (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    agent TEXT NOT NULL CHECK (agent IN ('bookkeeping', 'food_health')),
    conversation_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, agent)
);

CREATE TABLE IF NOT EXISTS user_secrets (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    secret_name TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, secret_name)
);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    bucket_key TEXT PRIMARY KEY,
    window_started_at INTEGER NOT NULL,
    request_count INTEGER NOT NULL
);
