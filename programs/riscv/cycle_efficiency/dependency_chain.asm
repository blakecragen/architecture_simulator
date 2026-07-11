; === Dependency Chain (width can't help) ===
; The SAME 16 instructions as ilp_parallel.asm by count, but every instruction
; reads the result of the one before it (a strict RAW chain on x1). There is no
; instruction-level parallelism to extract, so issuing wider cannot speed it up.
;
; Measured cycles-to-complete (this exact program):
;   single-cycle .... 16
;   multicycle ...... 48
;   pipeline ........ 20    (forwarding keeps the chain flowing, no stalls)
;   out-of-order .... 18
;   superscalar 2x .. 35    (NO speedup — the chain serialises the lanes)
;   superscalar 4x .. 35    (4 lanes are no better than 2: ILP is the limit)
;
; Takeaway: superscalar width only helps when instructions are INDEPENDENT.
; Here each ADD needs the previous result, so the wide machine gains nothing —
; and this simplified model actually spends EXTRA cycles because a same-group
; RAW dependency squashes the dependent lanes and re-fetches them (a documented
; superscalar simplification: intra-group hazards squash + re-fetch). Contrast
; with ilp_parallel.asm, where the same instruction count drops to 8 cycles at
; 4 lanes.
;
; Expected: x1 = 2^15 = 32768
; Best viewed with: Superscalar (compare 2 vs 4 lanes — the count doesn't move)

ADDI x1, x0, 1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
ADD  x1, x1, x1
