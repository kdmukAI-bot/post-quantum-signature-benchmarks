#!/usr/bin/env bash
# Round 4: copies the Pi Zero 2 W binaries named in the given plans, the queue script, and
# the plans to the board (ssh alias "pi02w", work dir /mnt/data/pq-bench/r4; override with
# PI_HOST and PI02W_DIR). Files go over ssh as a tar stream, as for the Pi Zero W (no SFTP
# server). The clock check's compress_bench comes from the build named by CLOCK_BUILD
# (default: the level-3 integer candidate) and lands in bin/clock/. Prints the SHA-256 of
# every copied file on both sides.
#
#   r4_pi02w_deploy.sh PLAN...   (plan file paths, such as scripts/r4_pi02w_plans/*.plan)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-pi02w}"
DIR="${PI02W_DIR:-/mnt/data/pq-bench/r4}"
CLOCK_BUILD="${CLOCK_BUILD:-r4-pi02w-shrincsB-asmrevbe-apinative-opto3-lto}"
SSH=(ssh -o BatchMode=yes "$HOST")
abs=()
for p in "$@"; do abs+=("$(cd "$(dirname "$p")" && pwd)/$(basename "$p")"); done
set -- "${abs[@]}"

builds=$(cat "$@" | grep -v -e '^#' -e '^$' | cut -d'|' -f1 | sort -u)
files=()
cd "$ROOT/harness/linux/build"
for b in $builds; do
    for f in pq_bench compress_bench armcap_probe; do
        [ -e "$b/$f" ] && files+=("$b/$f")
    done
done
"${SSH[@]}" "mkdir -p $DIR/bin/clock $DIR/plans"
tar cf - "${files[@]}" | "${SSH[@]}" "cd $DIR/bin && tar xf -"
tar cf - -C "$CLOCK_BUILD" compress_bench | "${SSH[@]}" "cd $DIR/bin/clock && tar xf -"
tar cf - -C "$HERE" r4_pi02w_queue.sh | "${SSH[@]}" "cd $DIR && tar xf - && chmod +x r4_pi02w_queue.sh"
plans=()
for p in "$@"; do plans+=("$(basename "$p")"); done
tar cf - -C "$(dirname "$1")" "${plans[@]}" | "${SSH[@]}" "cd $DIR/plans && tar xf -"
echo "== host"
sha256sum "${files[@]}" | sort -k2
(cd "$CLOCK_BUILD" && sha256sum compress_bench | sed 's|compress_bench|clock/compress_bench|')
(cd "$HERE" && sha256sum r4_pi02w_queue.sh)
(cd "$(dirname "$1")" && sha256sum "${plans[@]}" | sed 's|  |  plans/|')
echo "== $HOST"
"${SSH[@]}" "cd $DIR/bin && sha256sum ${files[*]} | sort -k2 && sha256sum clock/compress_bench && cd $DIR && sha256sum r4_pi02w_queue.sh ${plans[*]/#/plans/}"
