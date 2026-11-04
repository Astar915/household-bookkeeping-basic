-- Workflow params contain identifiers only. User messages, uploaded images,
-- provider secrets, and model responses remain encrypted in D1.
CREATE TABLE IF NOT EXISTS app_job_payloads (
    user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, operation_id),
    FOREIGN KEY (user_id, operation_id) REFERENCES app_jobs(user_id, operation_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS app_job_payload_chunks (
    user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    ciphertext TEXT NOT NULL,
    PRIMARY KEY (user_id, operation_id, generation_id, chunk_index),
    FOREIGN KEY (user_id, operation_id) REFERENCES app_jobs(user_id, operation_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_job_model_calls (
    user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    call_index INTEGER NOT NULL,
    request_hash TEXT NOT NULL,
    ledger_revision TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    response_bytes INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, operation_id, call_index),
    FOREIGN KEY (user_id, operation_id) REFERENCES app_jobs(user_id, operation_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS app_job_model_call_chunks (
    user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    call_index INTEGER NOT NULL,
    generation_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    ciphertext TEXT NOT NULL,
    PRIMARY KEY (user_id, operation_id, call_index, generation_id, chunk_index),
    FOREIGN KEY (user_id, operation_id, call_index)
        REFERENCES app_job_model_calls(user_id, operation_id, call_index) ON DELETE CASCADE
);
