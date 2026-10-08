#!/usr/bin/env bash
# Explicit governance phases. Install Wellman in WELLMAN_PYTHON separately.
set -euo pipefail

if [[ "${1:-}" == "access-codes" ]]; then
    shift
    exec ./backend/scripts/set_user_access_codes_local.sh "$@"
fi

WELLMAN_PYTHON="${WELLMAN_PYTHON:-python3}"
ANALYSIS_ENV="${ANALYSIS_ENV:-.wellman-tools}"
ANALYSIS_PYTHON="${ANALYSIS_PYTHON:-$ANALYSIS_ENV/bin/python}"
ANALYSIS_STORE="${ANALYSIS_STORE:-.wellman-analysis}"

usage() {
    cat <<'USAGE'
Usage: project2.sh preflight
       project2.sh update-tools
       project2.sh scan REPOSITORY [--exclude GLOB] [--timeout SECONDS]
       project2.sh plan REPOSITORY --catalog CATALOG.json [selection options]
       project2.sh access-codes [arguments]

Paths are relative to the current directory. Set WELLMAN_PYTHON to a runtime
with Wellman installed; ANALYSIS_ENV/ANALYSIS_PYTHON choose the separate pinned
analyzers. ANALYSIS_STORE must be outside the scanned Git repository.
Only update-tools installs packages. Scan publishes a complete snapshot or
keeps diagnostic evidence and the previous current pointer. Plan proposes
changes; --export-planfile explicitly creates human backlog tasks.
USAGE
}

command="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
case "$command" in
    help|-h|--help) usage ;;
    preflight)
        [[ $# -eq 0 ]] || { usage >&2; exit 2; }
        exec "$WELLMAN_PYTHON" -m wellman.analysis_environment preflight --python "$ANALYSIS_PYTHON"
        ;;
    update-tools)
        [[ $# -eq 0 ]] || { usage >&2; exit 2; }
        exec "$WELLMAN_PYTHON" -m wellman.analysis_environment update --environment "$ANALYSIS_ENV"
        ;;
    scan)
        [[ $# -gt 0 && "$1" != -* ]] || { usage >&2; exit 2; }
        repository="$1"; shift
        "$WELLMAN_PYTHON" -m wellman.analysis_environment preflight --python "$ANALYSIS_PYTHON" >&2
        exec "$WELLMAN_PYTHON" -m wellman.analyzer_snapshot "$repository" --output "$ANALYSIS_STORE" --python "$ANALYSIS_PYTHON" "$@"
        ;;
    plan)
        [[ $# -gt 0 && "$1" != -* ]] || { usage >&2; exit 2; }
        repository="$1"; shift
        exec "$WELLMAN_PYTHON" -m wellman.cli recommend --root "$repository" --selection-plan "$@"
        ;;
    *) usage >&2; exit 2 ;;
esac
