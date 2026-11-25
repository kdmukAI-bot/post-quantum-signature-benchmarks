# Environment: x86-64 host

The host reference outputs (a hash of every key and signature per message), the ML-DSA
attempt counts, and the PORS+FP tree work come from the host build of `harness/linux/`
(the Makefile's default target), made and run by `scripts/r2_host_reference.sh`. The lattice code runs its
integer floating-point emulation path, as on the boards. Host timings are not reported;
the files serve the correctness check (`scripts/check_r2.py`) and the expected-value fits
(`scripts/grind_fit_r2.py`).
