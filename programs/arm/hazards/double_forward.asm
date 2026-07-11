; === Double Forwarding Hazard ===
; Both source registers come from different pipeline stages simultaneously
; Expected: X1=10, X2=20, X3=30, X4=50
; Best viewed with: Pipeline

; Set up two independent values
MOVZ X1, #10           ; X1 = 10 (written cycle N)
MOVZ X2, #20           ; X2 = 20 (written cycle N+1)

; X3 reads both X1 and X2:
;   X1 is 2 stages ahead (MEM->EX forward)
;   X2 is 1 stage ahead (EX->EX forward)
ADD X3, X1, X2         ; X3 = 10 + 20 = 30 (double forward)

; Another double forward scenario
ADD X4, X3, X2         ; X4 = 30 + 20 = 50
;   X3 from EX->EX, X2 from MEM->EX

; Triple chain to keep pipeline busy
ADD X5, X4, X1         ; X5 = 50 + 10 = 60
ADD X6, X5, X3         ; X6 = 60 + 30 = 90

; Independent write then double forward
MOVZ X7, #5            ; X7 = 5
MOVZ X8, #15           ; X8 = 15
ADD X9, X7, X8         ; X9 = 5 + 15 = 20 (double forward again)
