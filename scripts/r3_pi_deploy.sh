#!/usr/bin/env bash
# Round 3: copy the Pi Zero W round-3 timing builds, the queue script, and the plan to the
# Pi (ssh alias "seedsigner", work dir /mnt/data/pq-bench/r3). A copy of
# scripts/r2_pi_deploy.sh with r2 replaced by r3. The Pi has no SFTP server, so files go
# over ssh as a tar stream. Prints the SHA-256 of every binary on both sides.
#
#   r3_pi_deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${PI_HOST:-seedsigner}"
DIR=/mnt/data/pq-bench/r3
cd "$ROOT/harness/linux/build"
ssh -o BatchMode=yes "$HOST" "mkdir -p $DIR/bin $DIR/plans"
tar cf - r3-armv6-*/pq_bench | ssh -o BatchMode=yes "$HOST" "cd $DIR/bin && tar xf -"
cd "$ROOT/scripts"
tar cf - r3_pi_queue.sh | ssh -o BatchMode=yes "$HOST" "cd $DIR && tar xf - && chmod +x r3_pi_queue.sh"
cd "$ROOT/scripts/r3_plans"
tar cf - pi0w.plan | ssh -o BatchMode=yes "$HOST" "cd $DIR/plans && tar xf -"
echo "== host"
(cd "$ROOT/harness/linux/build" && sha256sum r3-armv6-*/pq_bench)
(cd "$ROOT/scripts" && sha256sum r3_pi_queue.sh r3_plans/pi0w.plan)
echo "== $HOST"
ssh -o BatchMode=yes "$HOST" "cd $DIR/bin && sha256sum r3-armv6-*/pq_bench && cd $DIR && sha256sum r3_pi_queue.sh plans/pi0w.plan"
