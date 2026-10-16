-- Least-privilege application role (plan §8).
--
-- The runtime connects as `societas_app`: a LOGIN role that may read and write
-- rows in the application tables but owns nothing, cannot run DDL, and is not a
-- superuser. Migrations and schema changes run as the owner (POSTGRES_USER) —
-- this role is for the api/worker only.
--
-- Applied locally by compose's postgres initdb mount
-- (docker-entrypoint-initdb.d); a fresh volume runs it once. To apply it to an
-- existing database, run it as a superuser:
--
--     psql "$OWNER_DATABASE_URL" -f scripts/setup_db_roles.sql
--
-- PRODUCTION: the committed password below is a dev default. Set the real one
-- via the secret manager, e.g. `ALTER ROLE societas_app PASSWORD :'pw';`, and
-- point DATABASE_URL at this role.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'societas_app') THEN
    CREATE ROLE societas_app LOGIN PASSWORD 'societas_app_dev';
  END IF;
END
$$;

-- Connect to whichever database this runs against (the compose POSTGRES_DB).
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO societas_app', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO societas_app;

-- DML on the existing application tables and their sequences. No CREATE, no
-- ALTER, no DROP, no ownership — the runtime can only touch rows.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO societas_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO societas_app;

-- Tables/sequences a later migration creates are granted the same DML rights.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO societas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO societas_app;
