; === If-Else Branches (Branch Prediction) ===
; Series of forward branches with mixed taken/not-taken outcomes
; Tests predictor on forward conditional branches
; Expected: EAX=1, EBX=2, ECX=3, EDX=4
; Best viewed with: Pipeline

; --- Test 1: condition true, branch NOT taken (fall through) ---
MOV EAX, 5
CMP EAX, 10            ; 5 < 10, not equal
JE else1               ; NOT taken (5 != 10)
MOV EAX, 1             ; EAX = 1 (executed)
JMP end1
else1:
MOV EAX, 99
end1:

; --- Test 2: condition true, branch TAKEN ---
MOV EBX, 7
CMP EBX, 7             ; equal
JE then2               ; TAKEN (7 == 7)
MOV EBX, 99
JMP end2
then2:
MOV EBX, 2             ; EBX = 2
end2:

; --- Test 3: less-than, branch TAKEN ---
MOV ECX, 3
MOV EBP, ECX
SUB EBP, 8             ; EBP = 3 - 8 = -5
AND EBP, -128          ; non-zero if negative (3 < 8)
JNE then3              ; TAKEN: ECX < 8
MOV ECX, 99
JMP end3
then3:
MOV ECX, 3             ; ECX = 3
end3:

; --- Test 4: greater, branch NOT taken ---
MOV EDX, 2
MOV EBP, EDX
SUB EBP, 5             ; EBP = 2 - 5 = -3
JE not_greater4        ; equal -> not greater (not taken here)
AND EBP, -128          ; non-zero if negative (2 < 5), 0 if 2 > 5
JNE not_greater4       ; negative diff -> EDX < 5, skip else
JMP else4              ; positive diff -> EDX > 5, branch
not_greater4:
MOV EDX, 4             ; EDX = 4 (executed)
JMP end4
else4:
MOV EDX, 99
end4:
NOP
