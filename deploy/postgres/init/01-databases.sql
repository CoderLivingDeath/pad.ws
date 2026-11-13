-- Idempotently create the three service databases on the shared PostgreSQL instance.
-- This script is executed by psql during the official postgres image initialization.
-- The \gexec meta-command executes the generated SQL only when the database does not
-- already exist, so it is safe even if POSTGRES_DB created one of them.

SELECT 'CREATE DATABASE pad OWNER ' || quote_ident(current_user)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pad')\gexec

SELECT 'CREATE DATABASE keycloak OWNER ' || quote_ident(current_user)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak')\gexec

SELECT 'CREATE DATABASE coder OWNER ' || quote_ident(current_user)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'coder')\gexec
