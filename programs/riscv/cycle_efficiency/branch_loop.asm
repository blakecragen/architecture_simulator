; === Branch Cost & Prediction (control hazards) ===
; A counted loop summing 0..9. Every iteration ends in a taken branch, so this
; stresses the control path — where a deep pipeline pays a misprediction penalty
; that a single-cycle machine never sees.
;
; Measured cycles-to-complete (this exact program):
;   single-cycle ............ 34    (no pipeline, so no branch penalty)
;   multicycle .............. 103
;   pipeline (no predict) ... 64    (flush on every taken branch)
;   pipeline + bimodal ...... 49    (predictor learns the loop -> fewer flushes)
;   pipeline + gshare ....... 49
;   out-of-order ............ 56
;   superscalar 2x .......... 55    (competitive; but wider doesn't help here)
;   superscalar 4x .......... 64    (lane-0-only branch resolution: no width win)
;
; Takeaway: branches are the pipeline's enemy. The single-cycle model finishes
; in 34 because it has no pipeline to flush; the 5-stage pipeline balloons to 64
; paying a penalty per taken branch, and a branch predictor claws that back to
; 49. Turn on a predictor (dropdown) and re-run to watch the count fall.
;
; Expected: x1 = 45 (sum 0..9) ; mem[0] = 45
; Best viewed with: Pipeline (toggle the branch predictor on/off)

    ADDI x1, x0, 0        ; sum = 0
    ADDI x2, x0, 0        ; i = 0
    ADDI x3, x0, 10       ; n = 10
loop:
    ADD  x1, x1, x2       ; sum += i
    ADDI x2, x2, 1        ; i++
    BLT  x2, x3, loop     ; while (i < n)
    SW   x1, 0(x0)        ; mem[0] = sum
