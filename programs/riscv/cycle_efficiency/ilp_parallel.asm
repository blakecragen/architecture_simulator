; === ILP: Independent Ops (superscalar shines) ===
; 16 fully INDEPENDENT arithmetic instructions — no operand depends on a prior
; result, so a wide machine can issue several per cycle. This is the best case
; for superscalar width and the clearest way to see the models diverge.
;
; Measured cycles-to-complete (this exact program):
;   single-cycle .... 16    (1 instr / cycle)
;   multicycle ...... 48    (~3 cycles / instr: fetch, decode, execute phases)
;   pipeline ........ 20    (16 + pipe fill; no hazards to stall on)
;   out-of-order .... 18    (in-order commit drain dominates; 1-wide front end)
;   superscalar 2x .. 12    (two lanes retire in parallel)
;   superscalar 4x ...  8    (four lanes — 2x the throughput of 2 lanes)
;
; Takeaway: with real instruction-level parallelism, superscalar width pays off
; (16 -> 8), while the FetDecExe (multicycle) model pays a per-instruction phase
; tax (48). Compare this against dependency_chain.asm (same 16 instrs, zero ILP).
;
; Expected: x1=100, x2=200, x3=3 ... x16=16
; Best viewed with: Superscalar (bump the lanes slider 2 -> 4)

ADDI x1,  x0, 100
ADDI x2,  x0, 200
ADDI x3,  x0, 3
ADDI x4,  x0, 4
ADDI x5,  x0, 5
ADDI x6,  x0, 6
ADDI x7,  x0, 7
ADDI x8,  x0, 8
ADDI x9,  x0, 9
ADDI x10, x0, 10
ADDI x11, x0, 11
ADDI x12, x0, 12
ADDI x13, x0, 13
ADDI x14, x0, 14
ADDI x15, x0, 15
ADDI x16, x0, 16
