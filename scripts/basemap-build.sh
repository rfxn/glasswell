#!/usr/bin/env bash
# Build the self-hosted basemap: extract a region from a Protomaps planet build, record its
# vintage and checksum, and optionally fetch the font and sprite assets the label layers need.
# The archive is a manifested source like any regulator file — same rule, same evidence.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REGION_DIR="$SCRIPT_DIR/basemap-regions"
ASSETS_REPO=https://github.com/protomaps/basemaps-assets
BUILD_HOST=https://build.protomaps.com
FONTS=("Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic")

out_dir=./basemap
region=nd
maxzoom=13
build=latest
with_labels=0
dry_run=0
flavors=(dark grayscale)

usage() {
    cat <<'EOF'
usage: basemap-build.sh [options]

  --out DIR         where the archive and manifest land (default ./basemap)
  --region NAME     a file in scripts/basemap-regions (nd, nd-tx), or a path to a GeoJSON
  --bbox BOX        min_lon,min_lat,max_lon,max_lat instead of a region file
  --maxzoom N       highest zoom to extract (default 13)
  --build DATE      planet build to read, YYYYMMDD, or `latest` (default latest)
  --with-labels     also fetch fonts and sprites so the label layers can render
  --dry-run         report the size the extract would be, and download nothing

Measured sizes against the 2026-08-15 planet build (`--dry-run`):

  region  z0-10   z0-12   z0-13
  nd       ~6 MB   22 MB    48 MB
  nd-tx     24 MB  138 MB   336 MB

ND alone is the current ingest footprint; nd-tx is the Permian-ready extract. Each zoom
level roughly doubles the archive, so project from a low-maxzoom dry run before committing.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --*=*) set -- "${1%%=*}" "${1#*=}" "${@:2}"; continue ;;
        --out) out_dir="$2"; shift 2 ;;
        --region) region="$2"; shift 2 ;;
        --bbox) bbox="$2"; shift 2 ;;
        --maxzoom) maxzoom="$2"; shift 2 ;;
        --build) build="$2"; shift 2 ;;
        --with-labels) with_labels=1; shift ;;
        --dry-run) dry_run=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

if ! command -v pmtiles >/dev/null 2>&1; then
    cat >&2 <<EOF
pmtiles is not on PATH. Install the release binary for this host:

  curl -sL -o /tmp/go-pmtiles.tar.gz \\
    https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles_1.31.2_Linux_x86_64.tar.gz
  tar -xzf /tmp/go-pmtiles.tar.gz -C /usr/local/bin pmtiles
EOF
    exit 1
fi

if [[ "$build" == latest ]]; then
    build="$(date -u -d '3 days ago' +%Y%m%d)"
fi
source_url="$BUILD_HOST/$build.pmtiles"

extract_args=(--maxzoom="$maxzoom")
if [[ -n "${bbox:-}" ]]; then
    extract_args+=(--bbox="$bbox")
    region_label="bbox:$bbox"
else
    region_file="$region"
    [[ -f "$region_file" ]] || region_file="$REGION_DIR/$region.geojson"
    if [[ ! -f "$region_file" ]]; then
        printf 'no region file for %s (looked in %s)\n' "$region" "$REGION_DIR" >&2
        exit 1
    fi
    extract_args+=(--region="$region_file")
    region_label="$region"
fi

if [[ $dry_run -eq 1 ]]; then
    printf 'dry run: %s from %s at maxzoom %s\n' "$region_label" "$source_url" "$maxzoom"
    pmtiles extract "$source_url" /dev/null "${extract_args[@]}" --dry-run
    exit 0
fi

mkdir -p "$out_dir"
archive="$out_dir/basemap.pmtiles"
staging="$archive.new"

printf 'extracting %s from %s at maxzoom %s\n' "$region_label" "$source_url" "$maxzoom"
pmtiles extract "$source_url" "$staging" "${extract_args[@]}"

if [[ $with_labels -eq 1 ]]; then
    printf 'fetching label assets\n'
    assets_dir="$out_dir/.assets"
    rm -rf "$assets_dir"
    git clone --depth 1 "$ASSETS_REPO" "$assets_dir" >/dev/null 2>&1  # quiet: the clone is a fetch detail, not an event
    mkdir -p "$out_dir/fonts" "$out_dir/sprites"
    for font in "${FONTS[@]}"; do
        [[ -d "$assets_dir/fonts/$font" ]] && cp -r "$assets_dir/fonts/$font" "$out_dir/fonts/"
    done
    for flavor in "${flavors[@]}"; do
        for extension in json png; do
            for scale in "" @2x; do
                candidate="$assets_dir/sprites/v4/$flavor$scale.$extension"
                [[ -f "$candidate" ]] && cp "$candidate" "$out_dir/sprites/"
            done
        done
    done
    rm -rf "$assets_dir"
fi

mv "$staging" "$archive"
bytes="$(stat -c %s "$archive")"
sha="$(sha256sum "$archive" | cut -d' ' -f1)"
labels=false
[[ -d "$out_dir/fonts" ]] && labels=true

cat > "$out_dir/manifest.json" <<EOF
{
  "archive": "/basemap/basemap.pmtiles",
  "labels": $labels,
  "vintage": "$build",
  "region": "$region_label",
  "maxzoom": $maxzoom,
  "bytes": $bytes,
  "sha256": "$sha",
  "source": "$source_url",
  "licence": "ODbL (OpenStreetMap data) · BSD (Protomaps software)",
  "attribution": "© OpenStreetMap contributors"
}
EOF

printf 'wrote %s (%s bytes)\n' "$archive" "$bytes"
printf 'sha256 %s\n' "$sha"
printf 'manifest %s\n' "$out_dir/manifest.json"
