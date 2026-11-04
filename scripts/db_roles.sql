-- Ledger and compliance role split (plan §8, §12).
--
-- The money/compliance tables are tamper-evident by grant, not just by code:
--
--   * `societas_app` (api/worker) may APPEND usage events and read them, but
--     may not DELETE or rewrite an amount. The one mutation it needs is the
--     void path (`status`, `reason`), granted column-by-column.
--   * `societas_retention` is the only role that may DELETE aged rows from
--     `usage_events`, `llm_usage` and `webhook_events` — it is what
--     `scripts/purge_retention.py` should connect as.
--
-- Apply to an existing database as the owner/superuser after
-- `scripts/setup_db_roles.sql` has created `societas_app`:
--
--     psql "$OWNER_DATABASE_URL" -f scripts/db_roles.sql
--
-- In production, set each role's password from the secret manager; the dev
-- defaults live only in `setup_db_roles.sql`.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'societas_retention') THEN
    CREATE ROLE societas_retention LOGIN PASSWORD 'societas_retention_dev';
  END IF;
END
$$;

DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO societas_retention', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO societas_retention;

-- --- application role: append-only ledger ---------------------------------

REVOKE DELETE, TRUNCATE ON usage_events FROM societas_app;
REVOKE UPDATE ON usage_events FROM societas_app;
GRANT SELECT, INSERT ON usage_events TO societas_app;
-- The void path (`units.void_event`) flips status and records a reason.
GRANT UPDATE (status, reason) ON usage_events TO societas_app;

-- Reservations move both counters; the period row is not deletable.
REVOKE DELETE, TRUNCATE ON usage_periods FROM societas_app;
GRANT SELECT, INSERT, UPDATE ON usage_periods TO societas_app;

-- `setup_db_roles.sql` granted ALL on ALL TABLES; revoke the excess so this
-- script's posture is true even after that bootstrap.
REVOKE DELETE, TRUNCATE, UPDATE ON llm_usage FROM societas_app;
GRANT SELECT, INSERT ON llm_usage TO societas_app;

REVOKE DELETE, TRUNCATE ON webhook_events FROM societas_app;
GRANT SELECT, INSERT ON webhook_events TO societas_app;
-- The webhook processor marks an event processed/failed; no payload rewrite.
GRANT UPDATE (status, processed_at, error) ON webhook_events TO societas_app;

REVOKE DELETE, TRUNCATE ON subscriptions FROM societas_app;
GRANT SELECT, INSERT, UPDATE ON subscriptions TO societas_app;

REVOKE DELETE, TRUNCATE, UPDATE ON legal_documents FROM societas_app;
GRANT SELECT, INSERT ON legal_documents TO societas_app;

REVOKE DELETE, TRUNCATE, UPDATE ON user_consents FROM societas_app;
GRANT SELECT, INSERT ON user_consents TO societas_app;

-- --- retention role: age-based deletes only -------------------------------

GRANT SELECT, DELETE ON usage_events TO societas_retention;
GRANT SELECT, DELETE ON llm_usage TO societas_retention;
GRANT SELECT, DELETE ON webhook_events TO societas_retention;

-- Tables a later migration creates keep the same posture: append/read only.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO societas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE DELETE, TRUNCATE, UPDATE ON TABLES FROM societas_app;
