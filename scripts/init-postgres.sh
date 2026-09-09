#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 \
  --set=nautobot_password="$NAUTOBOT_DB_PASSWORD" \
  --set=temporal_password="$TEMPORAL_DB_PASSWORD" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE nautobot LOGIN PASSWORD %L', :'nautobot_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nautobot') \gexec

SELECT format('CREATE ROLE temporal LOGIN PASSWORD %L', :'temporal_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'temporal') \gexec

SELECT 'CREATE DATABASE nautobot OWNER nautobot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nautobot') \gexec

SELECT 'CREATE DATABASE temporal OWNER temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal') \gexec

SELECT 'CREATE DATABASE temporal_visibility OWNER temporal'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility') \gexec

REVOKE CONNECT ON DATABASE nautobot FROM PUBLIC;
REVOKE CONNECT ON DATABASE temporal FROM PUBLIC;
REVOKE CONNECT ON DATABASE temporal_visibility FROM PUBLIC;
GRANT CONNECT ON DATABASE nautobot TO nautobot;
GRANT CONNECT ON DATABASE temporal, temporal_visibility TO temporal;
SQL
