#!/usr/bin/env bash
set -euo pipefail

: "${PGDATABASE:?Set PGDATABASE and PostgreSQL connection variables via the environment or .pgpass}"
output="${1:-backups/sawa-$(date -u +%Y%m%dT%H%M%SZ).dump}"
umask 077
mkdir -p "$(dirname "$output")"
if [[ -e "$output" || -e "${output}.sha256" ]]; then
  echo "Refusing to overwrite an existing backup or checksum: $output" >&2
  exit 2
fi
temporary="${output}.tmp.$$"
trap 'rm -f "$temporary"' EXIT

# Credentials come from libpq environment variables or a protected .pgpass file,
# not a command-line connection URI that may appear in process listings. The custom
# archive is not client-encrypted: keep it on an encrypted volume and encrypt it
# before transferring it to external storage.
pg_dump --format=custom --no-owner --no-acl --file="$temporary"
pg_restore --list "$temporary" >/dev/null
mv -n -- "$temporary" "$output"
if [[ -e "$temporary" ]]; then
  echo "Backup target appeared during creation; refusing to overwrite it: $output" >&2
  exit 2
fi
checksum_temporary="${output}.sha256.tmp.$$"
trap 'rm -f "$temporary" "$checksum_temporary"' EXIT
sha256sum "$output" > "$checksum_temporary"
mv -n -- "$checksum_temporary" "${output}.sha256"
if [[ -e "$checksum_temporary" ]]; then
  echo "Checksum target appeared during creation; refusing to overwrite it: ${output}.sha256" >&2
  exit 2
fi
chmod 600 "$output" "${output}.sha256"
printf 'Backup verified: %s\n' "$output"
