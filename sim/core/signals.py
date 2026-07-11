# Shared control signal encodings used by all ISAs and execution models.
# ISA decoders map their opcodes → these enums. Execution models consume them.
# This is the contract that makes hot-swapping ISAs possible.


class AluOp:
    """ISA-agnostic ALU operation codes."""
    ADD  = 0
    SUB  = 1
    AND  = 2
    OR   = 3
    XOR  = 4
    SLT  = 5   # signed less-than
    SLTU = 6   # unsigned less-than
    SLL  = 7   # shift left logical
    SRL  = 8   # shift right logical
    SRA  = 9   # shift right arithmetic
    PASS = 10  # pass B unchanged (used for LUI)


ALU_OP_NAMES = {
    AluOp.ADD: "ADD", AluOp.SUB: "SUB", AluOp.AND: "AND",
    AluOp.OR: "OR", AluOp.XOR: "XOR", AluOp.SLT: "SLT",
    AluOp.SLTU: "SLTU", AluOp.SLL: "SLL", AluOp.SRL: "SRL",
    AluOp.SRA: "SRA", AluOp.PASS: "PASS",
}

WB_SEL_NAMES = {0: "ALU", 1: "MEMORY", 2: "PC4"}

BRANCH_COND_NAMES = {0: "NEVER", 1: "EQ", 2: "NEQ", 3: "LT", 4: "GE", 5: "LE", 6: "GT"}


class WBSel:
    """Writeback data source."""
    ALU    = 0   # ALU result
    MEMORY = 1   # data memory read
    PC4    = 2   # PC+4 (JAL/JALR link register)


class BranchCond:
    """Branch condition code, evaluated against ALU output by the execution model."""
    NEVER = 0   # not a branch instruction
    EQ    = 1   # taken if ALU zero flag set   (BEQ)
    NEQ   = 2   # taken if ALU zero flag clear (BNE)
    LT    = 3   # signed less-than
    GE    = 4   # signed greater-or-equal
    LE    = 5   # signed less-or-equal     (ARM B.LE / x86 JLE)
    GT    = 6   # signed greater-than      (ARM B.GT / x86 JG)


class JccCond:
    """x86 Jcc condition codes (low nibble of 0x7x opcode)."""
    JE  = 0x4   # ZF=1
    JNE = 0x5   # ZF=0
    JL  = 0xC   # SF!=OF (we use ALU SLT result)
    JGE = 0xD   # SF==OF
    JLE = 0xE   # ZF=1 or SF!=OF
    JG  = 0xF   # ZF=0 and SF==OF


JCC_COND_NAMES = {
    JccCond.JE: "JE", JccCond.JNE: "JNE", JccCond.JL: "JL",
    JccCond.JGE: "JGE", JccCond.JLE: "JLE", JccCond.JG: "JG",
}
