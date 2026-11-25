# SHRINCS stateless signing in Blockstream's Jade code

Notes for anyone calling `shrincs_sign_stateless()` and `shrincs_verify_stateless()` from
Blockstream's Jade fork (github.com/DmitriiKJ/Jade, branch `hash_based_signatures`, commit
`f5c90a5e`, `main/shrincs/`), or timing them. The firmware itself has no handler that
calls the stateless signer, so none of this is exercised by Jade's own request path.

## Zero the signature buffer before signing

`shrincs_sign_stateless()` writes the PORS+FP authentication set into a fixed area of
`M_MAX = 91` node slots but fills only as many slots as the set has nodes.
`shrincs_verify_stateless()` rejects the signature unless every unused slot is all zeros.
A buffer from `malloc()`, or one reused from an earlier signature, therefore gives
signatures that fail verification for some messages and pass for others.

Rule: pass a zeroed buffer of `SL_SIZE` bytes (2,568 for SHRINCS-B, 4,104 for SHRINCS-L).

## Signing time depends on the message: three grinding loops and the tree work

A stateless signature runs three searches whose attempt counts are geometric and different
for every message, and rebuilds a part of the PORS+FP tree whose size also depends on the
message:

- **PORS+FP grinding** (`pors_grind()` in `pors_fp.c`): tries counters until the K = 6
  leaf indices derived from the message digest have an Octopus authentication set of at
  most M_MAX = 91 nodes. The expected number of attempts is 1,659,626 for Jade's code
  (exact; `scripts/pors_fp_prob.py`), against a mean set size of about 119 nodes. Each
  attempt costs a PRF call, a message hash, and two or more SHA-256 blocks of index
  derivation.
- **WOTS+C grinding**, once in each of the D = 2 hypertree layers (`wots_grind()` via
  `xmss_sign()`), at the target sum `swn`. Expected attempts per layer: 6,218,398 for
  SHRINCS-L at swn = 140, and 748.0 for SHRINCS-B at swn = 2040 (exact:
  W^L / number of L-digit base-W strings with that digit sum).
- **PORS+FP authentication-path work** (`pors_auth_path()`): every authentication node
  is computed with `pors_treehash()`, which rebuilds the node's whole subtree. The
  subtrees of an Octopus set cover every leaf under the node where `pors_octopus()`
  stopped, except the K revealed ones. With n those leaves and |A| the set size, the work
  is 3n minus |A| hash calls (two per leaf, the secret value and the leaf hash; one per
  internal node). Without the early stop (section "Jade's Octopus count stops early") the
  stop node is the root and the whole tree of T = 9,245,141 leaves is rebuilt every time.
  With it, a message whose six leaves all lie under the leftmost node of level h rebuilds
  only that node's subtree: 0.06 of the tree at level 19, 0.32 at level 22, 0.55 at level
  23. The accepted sets are the clustered ones, so early stops are common: 56% of accepted
  sets stop below the root, and the expected work is 18,235,751 hash calls, 0.6575 of a
  whole-tree rebuild (exact: the dynamic program of `scripts/pors_fp_prob.py` split by
  stop level, `scripts/pors_stop_levels.py`; the stop levels of 200 benchmark messages
  follow this distribution).

The rest is a fixed cost dominated by the hypertree layers (each `xmss_sign()` computes a
whole 4,096-leaf tree, and layer 0's root is computed again for layer 1). So SHRINCS-L
stateless signing carries about 1.7 million PORS+FP attempts, 12.4 million WOTS+C
attempts, and 18.2 million tree hash calls on average, and SHRINCS-B the same PORS+FP and
tree work plus its larger hypertree layers.

Report the per-message expected value, as for SHRINCS-L stateful signing
(`shrincs-l-grinding-time-method.md`): fit

    time = fixed + k_pors x (PORS+FP attempts) + k_wots x (WOTS+C attempts, both layers)
           + k_tree x (tree hash calls)

and evaluate it at 1,659,626, 2 x E_wots, and 18,235,751. A message's tree hash calls
follow from its PORS+FP indices: recompute the message digest from the signature's R as
`pors_grind()` does, then call `pors_msg_to_indices()` and `pors_octopus()`
(`scripts/pors_work.c` computes these counts for the benchmark's messages 0 to 99; the fit
script is `scripts/grind_fit_r2.py`).

Rules:

- Do not fold the tree work into the fixed cost. On the Pi Zero W (level 3, ten messages)
  the fit without the tree term missed single runs by up to 38 s on times of 59 to 300 s
  and gave SHRINCS-B a negative WOTS+C cost. With it, no run missed by more than 0.31 s,
  and the cost per PORS+FP attempt and per tree hash agreed between SHRINCS-B and
  SHRINCS-L within 0.3% (the PORS+FP code and parameters are the same in both).
- A plain mean over ten messages is not an estimate of the expected time: the PORS+FP
  attempt count alone has a standard deviation about equal to its mean, and the tree work
  of ten messages can sit far from its expectation.

### Reading the counters from a signature

- WOTS+C counters: each layer's WOTS+C signature starts with R (32 bytes) and the counter
  (4 bytes, big-endian), at byte `N + PORS_SIGN_LEN + layer x XMSS_SIGN_LEN + R_LEN` of
  the stateless signature (`constants.h`).
- The PORS+FP counter is not stored. It is the `ctr` for which
  `prf_msg(sk_prf, pk_seed, opt_rand = pk_seed, message, len, 1, ctr, R_LEN, r)` gives the
  R at bytes `N .. N + 32` of the signature, so the signer can recover it by replaying the
  PRF from 0 (a few seconds on the slowest board, outside any timed section).

## Jade's Octopus count stops early

`pors_octopus()` ends its level loop as soon as the only node left at a level is node 0
(`if (I_len == 1 && I[0].b == 0) break;`). When all six chosen leaves lie under the
leftmost node of some level below the root, the siblings above that level are not part
of the authentication set, and the signer omits them. Because the sets that pass the
M_MAX test are the most clustered ones, this changes the acceptance probability from
3.958e-7 (a count of every sibling up to the root) to 6.025e-7, and the expected attempts
from 2,526,130 to 1,659,626. A Monte Carlo run of Jade's own functions (10^9 random
digests, 613 accepted, p = 6.13e-7 with a standard error of about 4%) agrees with the
second figure.

The early stop also shortens signing: the signer then rebuilds only the stop node's
subtree instead of the whole tree (see "PORS+FP authentication-path work" above).

Rule: compute expected attempts and expected tree work for the code as written. Whether
the early stop matches the SHRINCS specification, and what it means for the scheme, was
not examined here.

## Verification accepts only swn = SWN

Both `shrincs_verify_stateful()` and `shrincs_verify_stateless()` check WOTS+C digests
against the compile-time constant `SWN` (2040 for SHRINCS-B, 140 for SHRINCS-L), whatever
target the signer used. Signatures made at another target (for example SHRINCS-L at
swn = 96, as in Blockstream's benchmark table) are valid outputs of the signer but can
never verify.

## Dual-core paths

With the single-core define removed from `wots_c.c` (Blockstream's dual-core build), the
stateless signer uses both cores for the WOTS chain computations inside the hypertree
layer trees (`wots_pk_gen()`) and for the two WOTS+C grinds (even counters on core 0, odd
on core 1, as in stateful signing). The PORS+FP tree hashing and the PORS+FP grinding
have no dual-core path and run on one core. As with stateful signing, the WOTS+C counter
found on two cores can differ from the single-core one, so dual-core output bytes can
differ while still verifying; a fit for two cores splits the WOTS+C attempts by the
parity of each layer's counter and keeps the PORS+FP attempt and tree terms on one core.
