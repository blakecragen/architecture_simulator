# Cycle Efficiency Across Execution Models

Four RISC-V demo programs (in `programs/riscv/cycle_efficiency/`, and in the UI
under **Examples → Cycle Efficiency**) are crafted to make the five execution
models diverge in instructive ways. Load one, pick a model, and read the cycle
counter. The exact numbers below are pinned by
`tests/test_cycle_efficiency_demos.py`, which also checks that **every model
computes the same final result** — the cycle counts differ, the answer never
does.

"Cycles" = cycles to complete the work (the cycle after which registers +
memory stop changing).

| Program | single‑cycle | multicycle (FetDecExe) | pipeline | out‑of‑order | superscalar ×2 | superscalar ×4 |
|---|--:|--:|--:|--:|--:|--:|
| **ilp_parallel** — 16 independent ADDIs | 16 | 48 | 20 | 18 | 12 | **8** |
| **dependency_chain** — 16 ops, strict RAW chain | 16 | 48 | 20 | 18 | 35 | 35 |
| **mem_parallel** — 8 independent stores | 16 | 56 | 19 | 18 | 11 | **7** |
| **branch_loop** — sum 0..9 (taken branch/iter) | 34 | 103 | 64 | 56 | 55 | 64 |

`branch_loop` on the **pipeline** drops **64 → 49** cycles once a branch
predictor (bimodal / gshare) is enabled.

## What each model is showing

- **Single‑cycle** — one instruction per cycle, CPI = 1. It's the baseline and
  the oracle for correctness. It has no pipeline, so it *never* pays a branch
  penalty (`branch_loop` = 34, lower than every pipelined model).

- **Multicycle (FetDecExe)** — each instruction is broken into sequential phases
  (fetch → decode → execute → memory → writeback), so it spends ~3–5 cycles per
  instruction. It is always the highest count on straight‑line code (48–56 for
  16 instructions). The point isn't speed — it's that a short, simple datapath
  can be clocked faster per cycle.

- **Pipeline** — overlaps five instructions, so in steady state it approaches
  one instruction per cycle plus a fixed fill (`ilp_parallel` = 20 for 16
  instrs). Forwarding hides the RAW chain (`dependency_chain` = 20, no stalls),
  but taken branches flush the pipeline (`branch_loop` = 64), which a predictor
  partially recovers (49).

- **Out‑of‑order (Tomasulo)** — dynamic scheduling with in‑order commit. In this
  model the front end issues one instruction per cycle, so it doesn't beat the
  pipeline on raw ILP here; the ~18‑cycle floor on the straight‑line demos is
  the ROB commit drain. Its strength is tolerating latency and reordering around
  stalls rather than width.

- **Superscalar (N‑wide)** — issues up to N instructions per cycle. With real
  instruction‑level parallelism it wins big: `ilp_parallel` falls 16 → 12 → 8 as
  lanes go 1 → 2 → 4, and `mem_parallel` falls 16 → 11 → 7 because the data
  memory is **multi‑ported** (each lane has its own port; stores commit in
  program order; older same‑group stores forward to younger loads). Independent
  memory traffic now scales with width and **wider is never slower** — the old
  single‑port model made 4 lanes *slower* than 2 on `mem_parallel`.

## The catch: width needs parallelism

`dependency_chain` is the counter‑example. It has the same 16 instructions as
`ilp_parallel`, but every op depends on the previous one, so there is no ILP to
extract and extra lanes give **zero** benefit (×2 and ×4 are both 35). It's even
*higher* than the pipeline (20) because this simplified superscalar handles an
intra‑group hazard by squashing the dependent lanes and re‑fetching them, which
costs a bubble per squash. On `branch_loop` the lane‑0‑only branch resolution
shows the same "width doesn't help" ceiling — ×4 (64) is no better than ×2 (55)
— though it is no longer *slower* than the scalar pipeline.

This is a **documented modeling simplification**, distinct from the memory‑port
bottleneck that was fixed: intra‑group *register* RAW and *control* hazards
still squash‑and‑refetch, so dependency‑heavy or branch‑heavy code does not
benefit from — and can look worse under — superscalar width. Independent
compute and independent memory (the cases superscalar is meant to accelerate)
scale correctly. See `FUTURE_DIRECTIONS.md` for the analogous fix.

## Reproduce

```bash
python3 -m sim.harness --isa riscv --model superscalar --lanes 4 \
    --asm programs/riscv/cycle_efficiency/ilp_parallel.asm --cycles 40
python3 -m pytest tests/test_cycle_efficiency_demos.py -q
```

## Cycles ≠ time (and the Configurable model)

The table counts **cycles**, but cycles are not speed. Real execution time is:

```
time = cycles × clock period
```

Single-cycle has the **fewest** cycles (CPI = 1) but the **longest** clock
period, because one tick must do an instruction's entire datapath
(fetch → decode → ALU → memory → write-back). Pipelining/multi-cycle designs run
*more* cycles but a far shorter clock, so they usually finish in less *time*.
That's why single-cycle "wins" the cycle table yet is the design you'd never
build for speed.

The **Configurable** model makes this tangible. It reuses the single-cycle
datapath but lets you dial **cycles per instruction class** (ALU, load, store,
branch); it commits once, on each instruction's final cycle, so the *result* is
always identical to single-cycle — only the cycle count changes.

- Set every class to **1** → you've rebuilt single-cycle (fewest cycles).
- Set **{alu:3, load:4, store:4, branch:3}** → you've rebuilt the FetDecExe
  (multicycle) machine.

The UI models a clock period (`max(work / cycles)` across classes — the busiest
cycle sets the clock) and shows **cycles, clock period, and time = cycles ×
period**. Dial the budgets *down* toward single-cycle and the cycle count drops
but the clock period balloons; spread work over more cycles and the clock
shortens. Example (a small summing loop): single-cycle ≈ 28 cycles at period
6.0 → time 168; the FetDecExe profile ≈ 94 cycles at period 1.67 → time **157** —
*more cycles, less time*. That is the whole lesson, made adjustable.
