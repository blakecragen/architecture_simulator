; === Parallel Memory Writes (multi-port store throughput) ===
; Eight INDEPENDENT stores to eight distinct addresses, preceded by the loads of
; their values into registers. Because the addresses don't alias, a wide machine
; can commit several stores per cycle — this is the "assign an array in parallel"
; workload.
;
; Measured cycles-to-complete (this exact program):
;   single-cycle .... 16
;   multicycle ...... 56    (memory phase adds cycles per instruction)
;   pipeline ........ 19
;   out-of-order .... 18
;   superscalar 2x .. 11
;   superscalar 4x ...  7    (stores scale with lane width — monotonic)
;
; Takeaway: the superscalar data memory is MULTI-PORTED — each lane has its own
; port, stores commit in program order, and older same-group stores forward to
; younger loads. So independent memory traffic scales with width just like ALU
; work (16 -> 7), and wider is never slower. (Earlier a single shared port made
; 4 lanes slower than 2 on this workload; that bottleneck is gone.)
;
; Expected: x1=3 x2=6 ... x8=24 ; mem[0]=3 mem[4]=6 ... mem[28]=24
; Best viewed with: Superscalar (slide lanes 2 -> 4, watch the cycle count drop)

ADDI x1, x0, 3
ADDI x2, x0, 6
ADDI x3, x0, 9
ADDI x4, x0, 12
ADDI x5, x0, 15
ADDI x6, x0, 18
ADDI x7, x0, 21
ADDI x8, x0, 24
SW   x1, 0(x0)
SW   x2, 4(x0)
SW   x3, 8(x0)
SW   x4, 12(x0)
SW   x5, 16(x0)
SW   x6, 20(x0)
SW   x7, 24(x0)
SW   x8, 28(x0)
