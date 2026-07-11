# AArch64 (A64) encoding constants

# ── Condition codes (4-bit, used in B.cond) ─────────────────────
class A64Cond:
    EQ = 0x0   # Z=1
    NE = 0x1   # Z=0
    HS = 0x2   # C=1  (unsigned >=)
    LO = 0x3   # C=0  (unsigned <)
    MI = 0x4   # N=1
    PL = 0x5   # N=0
    HI = 0x8   # C=1 and Z=0 (unsigned >)
    LS = 0x9   # C=0 or Z=1  (unsigned <=)
    GE = 0xA   # N==V
    LT = 0xB   # N!=V
    GT = 0xC   # Z=0 and N==V
    LE = 0xD   # Z=1 or N!=V


# ── Bit-field helpers ───────────────────────────────────────────
def bits(val, hi, lo):
    """Extract bits [hi:lo] inclusive from val."""
    return (val >> lo) & ((1 << (hi - lo + 1)) - 1)


# ── Register names (AArch64) ───────────────────────────────────
REGISTER_NAMES = [f"X{i}" for i in range(31)] + ["XZR"]
# Index 31 = XZR (zero register for reads, SP in some contexts — we treat as zero)
