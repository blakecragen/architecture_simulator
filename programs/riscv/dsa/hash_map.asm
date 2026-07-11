; === Hash Map ===
; 8-bucket direct-mapped hash table
; Bucket format: [key (4B), value (4B)] = 8 bytes per bucket
; Hash function: key AND 7 (3-bit mask)
; Base address: 200
;
; Insert 4 key/value pairs:
;   key=3  -> bucket 3, value=100
;   key=10 -> bucket 2 (10&7=2), value=200
;   key=17 -> bucket 1 (17&7=1), value=300
;   key=24 -> bucket 0 (24&7=0), value=400
;
; Lookup key=10: expect value=200
;
; Expected: x10=200, x11=1
; Expected: mem[216]=10, mem[220]=200, mem[224]=3, mem[228]=100
; Cycles: 500
; Best viewed with: Any

ADDI x20, x0, 200      ; x20 = hash table base
ADDI x21, x0, 7        ; x21 = hash mask (8 buckets)

; --- Insert (key=3, value=100) ---
ADDI x1, x0, 3         ; x1 = key
ADDI x2, x0, 100       ; x2 = value
AND  x3, x1, x21       ; x3 = hash = 3 & 7 = 3
SLLI x3, x3, 3         ; x3 = bucket_offset = 3 * 8 = 24
ADD  x3, x20, x3       ; x3 = bucket_addr = 200 + 24 = 224
SW   x1, 0(x3)         ; bucket.key = 3
SW   x2, 4(x3)         ; bucket.value = 100

; --- Insert (key=10, value=200) ---
ADDI x1, x0, 10
ADDI x2, x0, 200
AND  x3, x1, x21       ; hash = 10 & 7 = 2
SLLI x3, x3, 3         ; offset = 2 * 8 = 16
ADD  x3, x20, x3       ; addr = 200 + 16 = 216
SW   x1, 0(x3)
SW   x2, 4(x3)

; --- Insert (key=17, value=300) ---
ADDI x1, x0, 17
ADDI x2, x0, 300
AND  x3, x1, x21       ; hash = 17 & 7 = 1
SLLI x3, x3, 3         ; offset = 1 * 8 = 8
ADD  x3, x20, x3       ; addr = 200 + 8 = 208
SW   x1, 0(x3)
SW   x2, 4(x3)

; --- Insert (key=24, value=400) ---
ADDI x1, x0, 24
ADDI x2, x0, 400
AND  x3, x1, x21       ; hash = 24 & 7 = 0
SLLI x3, x3, 3         ; offset = 0 * 8 = 0
ADD  x3, x20, x3       ; addr = 200 + 0 = 200
SW   x1, 0(x3)
SW   x2, 4(x3)

; --- Lookup key=10 ---
ADDI x1, x0, 10        ; x1 = lookup key
AND  x3, x1, x21       ; hash = 10 & 7 = 2
SLLI x3, x3, 3         ; offset = 16
ADD  x3, x20, x3       ; addr = 216
LW   x4, 0(x3)         ; x4 = stored key
LW   x10, 4(x3)        ; x10 = stored value (200)

; Verify key matches
BEQ  x4, x1, found     ; if stored_key == lookup_key, found
ADDI x11, x0, 0        ; x11 = 0 (not found)
JAL  x0, done

found:
ADDI x11, x0, 1        ; x11 = 1 (found)

done:
; x10 = 200, x11 = 1
NOP
