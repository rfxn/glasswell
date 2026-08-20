#!/bin/bash
# SB-06 section 7.4 / section 11 step 27 — restore the newest pg_dump into a scratch
# database, assert it restores clean, then drop it.
set -uo pipefail

PGDUMP_DIR=/data/backups/pg
SCRATCH=glasswell_restore_test
SRC=glasswell

newest=""
newest_ts=0
shopt -s nullglob
for f in "$PGDUMP_DIR"/glasswell-*.dump; do
	ts=$(stat -c %Y "$f") || continue
	if [ "$ts" -gt "$newest_ts" ]; then newest_ts="$ts"; newest="$f"; fi
done
[ -n "$newest" ] || { echo "FAIL: no dump found in $PGDUMP_DIR"; exit 1; }
echo "restoring: $newest ($(stat -c %s "$newest") bytes)"

runuser -u postgres -- psql -tAc "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null || exit 1
runuser -u postgres -- createdb -O glasswell "$SCRATCH" || { echo "FAIL: createdb"; exit 1; }

echo "--- pg_restore (strict, --exit-on-error) ---"
if runuser -u postgres -- pg_restore --exit-on-error --dbname "$SCRATCH" "$newest"; then
	echo "RESTORE_EXIT=0"
else
	rc=$?
	echo "FAIL: pg_restore exited $rc"
	runuser -u postgres -- psql -tAc "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null
	exit 1
fi

echo "--- assertions against the restored database ---"
runuser -u postgres -- psql -d "$SCRATCH" -tAc \
	"SELECT 'postgis=' || postgis_version();" || exit 1
runuser -u postgres -- psql -d "$SCRATCH" -tAc \
	"SELECT 'extensions=' || string_agg(extname, ',' ORDER BY extname) FROM pg_extension;" || exit 1
runuser -u postgres -- psql -d "$SCRATCH" -tAc \
	"SELECT 'owner=' || pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname = '$SCRATCH';" || exit 1

echo "--- source vs restored: user-table count must match ---"
q="SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema','topology');"
src_n=$(runuser -u postgres -- psql -d "$SRC" -tAc "$q" | tr -d ' ')
dst_n=$(runuser -u postgres -- psql -d "$SCRATCH" -tAc "$q" | tr -d ' ')
echo "source=$src_n restored=$dst_n"
if [ "$src_n" != "$dst_n" ]; then
	echo "FAIL: table count mismatch"
	runuser -u postgres -- psql -tAc "DROP DATABASE IF EXISTS $SCRATCH;" >/dev/null
	exit 1
fi

echo "--- dropping scratch database ---"
runuser -u postgres -- psql -tAc "DROP DATABASE $SCRATCH;" || { echo "FAIL: drop"; exit 1; }
runuser -u postgres -- psql -tAc "SELECT count(*) FROM pg_database WHERE datname='$SCRATCH';" | \
	grep -qx ' *0' && echo "scratch database removed"

echo "OK: restore drill passed"
