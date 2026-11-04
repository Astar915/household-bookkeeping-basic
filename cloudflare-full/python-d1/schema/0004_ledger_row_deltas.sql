-- Keep an immutable SQLite base snapshot and layer only changed ledger rows
-- over it. Staged deltas are invisible until user_state_roots advances.
CREATE TABLE IF NOT EXISTS user_ledger_row_deltas (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert','delete')),
    row_json TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, table_name, row_key),
    CHECK ((operation='upsert' AND row_json IS NOT NULL) OR (operation='delete' AND row_json IS NULL))
);

CREATE TABLE IF NOT EXISTS user_ledger_row_delta_stage (
    user_id TEXT NOT NULL REFERENCES cloud_users(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('upsert','delete')),
    row_json TEXT,
    PRIMARY KEY (user_id, stage_id, table_name, row_key),
    CHECK ((operation='upsert' AND row_json IS NOT NULL) OR (operation='delete' AND row_json IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_user_ledger_row_delta_stage
    ON user_ledger_row_delta_stage(user_id, stage_id);
