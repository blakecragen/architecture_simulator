; === Tight Loop (Branch Prediction) ===
; Backward branch taken 19 out of 20 iterations
; Tests predictor accuracy on a simple counted loop
; Expected: EAX=20, EBX=20
; Best viewed with: Pipeline

; --- Count from 0 to 20 ---
MOV EAX, 0             ; EAX = counter = 0
MOV ECX, 20            ; ECX = limit = 20
loop:
ADD EAX, 1             ; EAX++
CMP EAX, ECX           ; compare counter with limit
JNE loop               ; backward branch: taken 19 times, falls through once

; --- Copy result ---
MOV EBX, EAX           ; EBX = 20
