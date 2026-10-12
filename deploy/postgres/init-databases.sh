#!/bin/sh
# Runs once, when the Postgres volume is empty (docker-entrypoint-initdb.d), as the superuser.
# Creates the KnoBridge application database and the Temporal databases, each with its own role.
# Names and passwords come from the compose environment (see .env.example).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v app_db="$KNOBRIDGE_DB_NAME" \
  -v app_user="$KNOBRIDGE_DB_USER" \
  -v app_password="$KNOBRIDGE_DB_PASSWORD" \
  -v temporal_user="$TEMPORAL_DB_USER" \
  -v temporal_password="$TEMPORAL_DB_PASSWORD" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
CREATE DATABASE :"app_db" OWNER :"app_user";

-- Temporal auto-setup runs with SKIP_DB_CREATE=true: it only applies its schemas here.
CREATE ROLE :"temporal_user" LOGIN PASSWORD :'temporal_password';
CREATE DATABASE temporal OWNER :"temporal_user";
CREATE DATABASE temporal_visibility OWNER :"temporal_user";

-- pgvector is not a trusted extension, so the superuser creates it; the first Alembic
-- migration (CREATE EXTENSION IF NOT EXISTS vector) then finds it and does nothing.
\connect :"app_db"
CREATE EXTENSION IF NOT EXISTS vector;
SQL
