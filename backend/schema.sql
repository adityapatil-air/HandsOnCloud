-- CloudProof PostgreSQL Schema
-- Run once on a fresh RDS instance:
-- psql -h <DB_HOST> -U <DB_USER> -d <DB_NAME> -f schema.sql
-- OR on EC2:
-- venv/bin/python -c "
--   import psycopg2, os
--   from dotenv import load_dotenv
--   load_dotenv()
--   conn = psycopg2.connect(host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT','5432'), database=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'))
--   conn.cursor().execute(open('schema.sql').read())
--   conn.commit()
--   print('Done')
-- "

CREATE TABLE IF NOT EXISTS users (
    id                        SERIAL PRIMARY KEY,
    username                  TEXT UNIQUE,
    name                      TEXT NOT NULL,
    email                     TEXT UNIQUE NOT NULL,
    password_hash             TEXT,
    email_verified            INTEGER DEFAULT 0,
    firebase_uid              TEXT UNIQUE,
    oauth_provider            TEXT,
    oauth_id                  TEXT,
    role_arn                  TEXT,
    s3_bucket                 TEXT,
    s3_prefix                 TEXT DEFAULT '',
    aws_region                TEXT DEFAULT 'us-east-1',
    sync_pin_hash             TEXT,
    aws_access_key_encrypted  TEXT,
    aws_secret_key_encrypted  TEXT,
    aws_account_id            TEXT,
    aws_user_arn              TEXT,
    last_auto_synced_at       TIMESTAMP,
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    used        INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    used        INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    service     TEXT NOT NULL,
    action      TEXT NOT NULL,
    score       INTEGER NOT NULL,
    event_id    TEXT,
    timestamp   TIMESTAMP,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_id)
);

CREATE TABLE IF NOT EXISTS daily_scores (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date         DATE NOT NULL,
    total_score  INTEGER NOT NULL,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS processing_state (
    id                         SERIAL PRIMARY KEY,
    user_id                    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_processed_timestamp   TIMESTAMP NOT NULL,
    UNIQUE(user_id)
);

CREATE TABLE IF NOT EXISTS resource_state (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource_type       TEXT NOT NULL,
    resource_id         TEXT NOT NULL,
    parent_resource_id  TEXT,
    state               TEXT NOT NULL,
    metadata            TEXT,
    last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, resource_type, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user_date  ON activity_logs(user_id, date);
CREATE INDEX IF NOT EXISTS idx_activity_logs_event_id   ON activity_logs(user_id, event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_scores_user_date   ON daily_scores(user_id, date);
CREATE INDEX IF NOT EXISTS idx_resource_state_user      ON resource_state(user_id, resource_type, state);
