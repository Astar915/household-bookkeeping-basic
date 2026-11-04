ALTER TABLE cloud_sessions
    ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'github';

CREATE TABLE IF NOT EXISTS cloud_gitee_identities (
    gitee_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES cloud_users(id) ON DELETE CASCADE,
    gitee_login TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_gitee_identities_user
    ON cloud_gitee_identities(user_id);

CREATE TABLE IF NOT EXISTS gitee_login_flows (
    flow_id TEXT PRIMARY KEY,
    state_hash TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK(mode IN ('login','link')),
    link_user_id TEXT REFERENCES cloud_users(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK(state IN ('pending','processing','consumed','failed','cancelled')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gitee_login_flows_expiry
    ON gitee_login_flows(expires_at);
