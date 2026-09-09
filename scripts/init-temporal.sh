#!/bin/sh
set -eu

export SQL_HOST="$POSTGRES_SEEDS"
export SQL_PORT="${DB_PORT:-5432}"
export SQL_USER="$POSTGRES_USER"

for database_and_schema in \
  "temporal:/etc/temporal/schema/postgresql/v12/temporal/versioned" \
  "temporal_visibility:/etc/temporal/schema/postgresql/v12/visibility/versioned"
do
  database=${database_and_schema%%:*}
  schema_dir=${database_and_schema#*:}

  temporal-sql-tool \
    --plugin postgres12 \
    --database "$database" \
    setup-schema --version 0.0

  temporal-sql-tool \
    --plugin postgres12 \
    --database "$database" \
    update-schema --schema-dir "$schema_dir"
done
