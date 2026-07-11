# RISC-V RV32I constants


class Opcode:
    R_TYPE  = 0b0110011   # ADD SUB AND OR XOR SLT SLL SRL SRA
    I_ALU   = 0b0010011   # ADDI ANDI ORI XORI SLTI SLTIU SLLI SRLI SRAI
    LOAD    = 0b0000011   # LW LH LB LHU LBU
    STORE   = 0b0100011   # SW SH SB
    BRANCH  = 0b1100011   # BEQ BNE BLT BGE BLTU BGEU
    JAL     = 0b1101111
    JALR    = 0b1100111
    LUI     = 0b0110111
    AUIPC   = 0b0010111
    SYSTEM  = 0b1110011   # ECALL EBREAK (stub)


class Funct3:
    # Integer ALU
    ADD_SUB = 0b000
    SLL     = 0b001
    SLT     = 0b010
    SLTU    = 0b011
    XOR     = 0b100
    SRL_SRA = 0b101
    OR      = 0b110
    AND     = 0b111

    # Branch
    BEQ     = 0b000
    BNE     = 0b001
    BLT     = 0b100
    BGE     = 0b101
    BLTU    = 0b110
    BGEU    = 0b111

    # Load/Store width
    BYTE    = 0b000
    HALF    = 0b001
    WORD    = 0b010
    BYTE_U  = 0b100
    HALF_U  = 0b101


class Funct7:
    NORMAL  = 0b0000000
    ALT     = 0b0100000   # SUB, SRA


# ABI register names (index = register number)
REGISTER_NAMES = [
    "zero", "ra",  "sp",  "gp",  "tp",
    "t0",   "t1",  "t2",
    "s0",   "s1",
    "a0",   "a1",  "a2",  "a3",  "a4",  "a5",  "a6",  "a7",
    "s2",   "s3",  "s4",  "s5",  "s6",  "s7",  "s8",  "s9",  "s10", "s11",
    "t3",   "t4",  "t5",  "t6",
]
