# x86-32 encoding constants

# ── Register encoding ────────────────────────────────────────────
REG_EAX = 0
REG_ECX = 1
REG_EDX = 2
REG_EBX = 3
REG_ESP = 4
REG_EBP = 5
REG_ESI = 6
REG_EDI = 7

REGISTER_NAMES = ["EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI"]

# ── Opcode constants ─────────────────────────────────────────────
OP_NOP      = 0x90
OP_RET      = 0xC3
OP_PUSH_BASE = 0x50   # 0x50+r
OP_POP_BASE  = 0x58   # 0x58+r
OP_MOV_IMM_BASE = 0xB8  # 0xB8+r (MOV r32, imm32)

OP_ADD_R32  = 0x01   # ADD r/m32, r32
OP_OR_R32   = 0x09   # OR  r/m32, r32
OP_AND_R32  = 0x21   # AND r/m32, r32
OP_SUB_R32  = 0x29   # SUB r/m32, r32
OP_XOR_R32  = 0x31   # XOR r/m32, r32
OP_CMP_R32  = 0x39   # CMP r/m32, r32

OP_MOV_RM_R = 0x89   # MOV r/m32, r32 (also reg-reg with mod=11)
OP_MOV_R_RM = 0x8B   # MOV r32, r/m32

OP_IMM_GRP1 = 0x83   # Group 1: ADD/SUB/CMP r/m32, imm8

OP_JMP_REL8 = 0xEB   # JMP rel8
OP_CALL_REL32 = 0xE8 # CALL rel32

# Jcc rel8 range: 0x70–0x7F
OP_JCC_BASE = 0x70

# ── ModRM helpers ────────────────────────────────────────────────
def modrm_mod(b):
    """Extract mod field [7:6]."""
    return (b >> 6) & 0x3

def modrm_reg(b):
    """Extract reg field [5:3]."""
    return (b >> 3) & 0x7

def modrm_rm(b):
    """Extract r/m field [2:0]."""
    return b & 0x7


# ── Group 1 extension opcodes (from ModRM reg field) ─────────────
GRP1_ADD = 0  # /0
GRP1_OR  = 1  # /1
GRP1_AND = 4  # /4
GRP1_SUB = 5  # /5
GRP1_XOR = 6  # /6
GRP1_CMP = 7  # /7
