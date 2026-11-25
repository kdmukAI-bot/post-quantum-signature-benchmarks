# The RP2350 SHA-256 accelerator cannot resume from a given state

Hash-based signature code (SLH-DSA through slhdsa-c, SPHINCS+, SHRINCS, XMSS) computes
most of its millions of hashes from a precomputed state: the SHA-256 state after one
64-byte block holding PK.seed and zero padding. On chips whose SHA unit accepts a state
(the ESP32-S3 and ESP32-P4, `SOC_SHA_SUPPORT_RESUME`; see
`esp32-sha-unit-raw-compression.md`), a raw compression function backed by the unit is
enough. The RP2350's accelerator does not accept one, which changes how it can be used.

## What the accelerator does

From the register descriptions (RP2350 datasheet; the Pico SDK's
`hardware/regs/sha256.h`), checked on the device:

- One engine shared by both cores, fed 32 bits at a time through WDATA, by the CPU or by
  DMA (DREQ_SHA256). With CSR.BSWAP set (the default), a byte buffer can be written as
  little-endian words.
- CSR.START loads the SHA-256 initial value and clears the engine. After 16 words the
  engine digests the block; WDATA_RDY is low for 57 cycles, and the next 16 words continue
  from the new state. SUM0 to SUM7 then hold that state (SUM_VLD high).
- **No state input.** SUM0 to SUM7 are read-only. On the device, writes to them left them
  unchanged, and the next block continued from the engine's own state, not from the
  written values. Nothing else takes a chaining value.
- A word written while WDATA_RDY is low is dropped and sets the sticky ERR_WDATA_NOT_RDY
  flag (write one to clear).
- The SDK's `pico_sha256` hashes whole messages with its own padding; it has no call for
  one compression. The lower-level `hardware_sha256` functions (start, put word, wait,
  read result) are the documented way to drive single blocks.

## Rule

To serve a compression from an arbitrary state, rebuild that state on the engine: START,
then write the block(s) that lead from the initial value to it, then the new block. For
signature code this is cheap because the reused state is one block from the initial value.
Three cases need no replay: a block from the initial value (START, write it), and a block
that continues the engine's own last result (write it). A state that cannot be rebuilt
must be computed in software.

`harness/pico/sha256_rphw.h` implements this behind slhdsa-c's `sha2_256_compress()`: it
keeps the engine's last result, remembers every one-block state with its block (a ring of
eight, plus the entry used last), and compares 32-byte states to pick the path. Results
are identical to portable C by construction (equal states are the same state); 1,000
random cases per path and every benchmark output matched.

## What it costs

CPU cycles per compression on core 0 at 150 MHz, code in flash, -O2 (microbenchmark,
`harness/pico/microbench_rp.c`):

| Path | From initial value | Continuation | Replay |
|---|---|---|---|
| Registers | 444 | 302 | 484 |
| SDK `hardware_sha256` functions | 576 | 433 | 662 |
| DMA (replay: both blocks in one transfer from a copied buffer) | 445 | 310 | 567 |
| Portable C (slhdsa-c), for comparison | 2,952 | | |
| OpenSSL 3.4.1's ARMv4 assembly, assembled as Thumb-2, for comparison | 2,329 | | |

Pieces: START plus 16 word writes 87 cycles (5.4 per write), the wait for the digest about
63 cycles, reading the 8 sums 44 cycles. The replay's second block is the price of the
missing state input; the engine is still about six times faster than portable C per
compression. In whole SLH-DSA-SHA2-128s signatures nearly every compression is a replay
(2,188,007 of 2,220,338; the rest continuations and initial values; none fell back to
software).

## Traps

- **Two DMA transfers for one replay can stall.** Writing the remembered block with one
  DMA transfer and the new block with a second transfer, triggered after the first
  completes, hung the engine on the device: the second trigger can come after the engine
  has raised its request for the next block, and the request is not seen again. One
  transfer over both blocks (from a buffer they are copied into, as `pico_sha256` feeds a
  long message) works. DMA did not beat CPU writes for these short inputs.
- **Write all 16 words of a block only when WDATA_RDY is high.** A 17th word written
  straight after the 16th is dropped (ERR_WDATA_NOT_RDY), and the hash is wrong.
- **One engine, two cores.** As on the ESP32 boards, let one core hold the engine for a
  whole operation and give the other core a software path; the engine's last result and
  the remembered states are shared data, valid only for the core that holds it.
