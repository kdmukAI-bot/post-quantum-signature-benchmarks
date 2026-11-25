#!/usr/bin/env bash
# Round 2: copy the Pi Zero W builds, the queue script, and the plans to the Pi (ssh alias
# "seedsigner", work dir /mnt/data/pq-bench/r2). The Pi has no SFTP server, so files go
# over ssh as a tar stream. Prints the SHA-256 of every binary on both sides.
#
#   r2_pi_deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-seedsigner}"
DIR=/mnt/data/pq-bench/r2
cd "$ROOT/harness/linux/build"
ssh -o BatchMode=yes "$HOST" "mkdir -p $DIR/bin $DIR/plans"
tar cf - r2-armv6-*/pq_bench | ssh -o BatchMode=yes "$HOST" "cd $DIR/bin && tar xf -"
cd "$ROOT/scripts"
tar cf - r2_pi_queue.sh | ssh -o BatchMode=yes "$HOST" "cd $DIR && tar xf - && chmod +x r2_pi_queue.sh"
cd "$ROOT/scripts/r2_plans"
tar cf - pi0w.plan | ssh -o BatchMode=yes "$HOST" "cd $DIR/plans && tar xf -"
echo "== host"
(cd "$ROOT/harness/linux/build" && sha256sum r2-armv6-*/pq_bench)
echo "== $HOST"
ssh -o BatchMode=yes "$HOST" "cd $DIR/bin && sha256sum r2-armv6-*/pq_bench"
