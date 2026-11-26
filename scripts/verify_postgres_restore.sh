#!/usr/bin/env bash
set -euo pipefail

backup_file="${1:?Usage: verify_postgres_restore.sh BACKUP.dump}"
: "${PGDATABASE:?Set PGDATABASE to the source database name}"
: "${RESTORE_TARGET_DATABASE:?Set RESTORE_TARGET_DATABASE to a disposable empty database}"
: "${RESTORE_TARGET_CONFIRMATION:?Set RESTORE_TARGET_CONFIRMATION to the exact target database name}"

case "${APP_ENV:-}" in
  [Pp][Rr][Oo][Dd][Uu][Cc][Tt][Ii][Oo][Nn])
    echo "Refusing restore verification while APP_ENV=production." >&2
    exit 2
    ;;
esac
if [[ "$RESTORE_TARGET_DATABASE" == "$PGDATABASE" || "$RESTORE_TARGET_CONFIRMATION" != "$RESTORE_TARGET_DATABASE" ]]; then
  echo "Source and target must differ, and the target name must be explicitly confirmed." >&2
  exit 2
fi
if [[ ! -r "$backup_file" ]]; then
  echo "Backup file is not readable: $backup_file" >&2
  exit 2
fi

pg_restore --list "$backup_file" >/dev/null
existing_objects="$(psql --dbname="$RESTORE_TARGET_DATABASE" --no-psqlrc --tuples-only --no-align \
  --command="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND c.relkind IN ('r','p','v','m','S','f');")"
if [[ "$existing_objects" != "0" ]]; then
  echo "Restore target is not empty; refusing to overwrite it." >&2
  exit 2
fi

pg_restore --dbname="$RESTORE_TARGET_DATABASE" --exit-on-error --single-transaction --no-owner --no-acl "$backup_file"
users_table="$(psql --dbname="$RESTORE_TARGET_DATABASE" --no-psqlrc --tuples-only --no-align \
  --command="SELECT to_regclass('public.users') IS NOT NULL;")"
if [[ "$users_table" != "t" ]]; then
  echo "Restore completed without the expected users table." >&2
  exit 1
fi
printf 'Restore verification passed into disposable database: %s\n' "$RESTORE_TARGET_DATABASE"
