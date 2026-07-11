; === Memory Instructions ===
; Exercise LW, SW — store values then load them back
; Expected: x3=42, x4=99, x5=42, x6=99
; Best viewed with: Any

; --- Set up values to store ---
ADDI x1, x0, 42        ; x1 = 42
ADDI x2, x0, 99        ; x2 = 99

; --- Store to memory at addresses 0 and 4 ---
SW   x1, 0(x0)         ; mem[0] = 42
SW   x2, 4(x0)         ; mem[4] = 99

; --- Load them back into different registers ---
LW   x3, 0(x0)         ; x3 = mem[0] = 42
LW   x4, 4(x0)         ; x4 = mem[4] = 99

; --- Store with base + offset ---
ADDI x7, x0, 8         ; x7 = 8 (base address)
SW   x1, 0(x7)         ; mem[8] = 42
SW   x2, 4(x7)         ; mem[12] = 99

; --- Load back using same base + offset ---
LW   x5, 0(x7)         ; x5 = mem[8] = 42
LW   x6, 4(x7)         ; x6 = mem[12] = 99
