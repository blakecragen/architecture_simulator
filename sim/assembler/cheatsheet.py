"""
Per-ISA assembly cheatsheet data for the UI.

Returns structured data that the frontend can render as a quick-reference card.
"""


def get_cheatsheet(isa_name: str) -> list[dict]:
    """Return [{category, mnemonic, syntax, description, example}, ...] for the given ISA."""
    key = isa_name.strip().lower()
    if key == 'riscv':
        return _riscv_cheatsheet()
    elif key == 'arm':
        return _arm_cheatsheet()
    elif key == 'x86':
        return _x86_cheatsheet()
    else:
        raise ValueError(f"Unknown ISA '{isa_name}'. Supported: riscv, arm, x86")


def _riscv_cheatsheet() -> list[dict]:
    return [
        # ── Arithmetic (R-type) ─────────────────────────────────────
        {"category": "Arithmetic",  "mnemonic": "ADD",   "syntax": "ADD rd, rs1, rs2",    "description": "rd = rs1 + rs2",                    "example": "ADD x3, x1, x2"},
        {"category": "Arithmetic",  "mnemonic": "SUB",   "syntax": "SUB rd, rs1, rs2",    "description": "rd = rs1 - rs2",                    "example": "SUB x4, x1, x2"},
        {"category": "Arithmetic",  "mnemonic": "SLT",   "syntax": "SLT rd, rs1, rs2",    "description": "rd = (rs1 < rs2) ? 1 : 0 (signed)", "example": "SLT x3, x1, x2"},
        {"category": "Arithmetic",  "mnemonic": "SLTU",  "syntax": "SLTU rd, rs1, rs2",   "description": "rd = (rs1 < rs2) ? 1 : 0 (unsigned)", "example": "SLTU x3, x1, x2"},

        # ── Logical (R-type) ────────────────────────────────────────
        {"category": "Logical",     "mnemonic": "AND",   "syntax": "AND rd, rs1, rs2",    "description": "rd = rs1 & rs2",                    "example": "AND x3, x1, x2"},
        {"category": "Logical",     "mnemonic": "OR",    "syntax": "OR rd, rs1, rs2",     "description": "rd = rs1 | rs2",                    "example": "OR x3, x1, x2"},
        {"category": "Logical",     "mnemonic": "XOR",   "syntax": "XOR rd, rs1, rs2",    "description": "rd = rs1 ^ rs2",                    "example": "XOR x3, x1, x2"},

        # ── Shift (R-type) ──────────────────────────────────────────
        {"category": "Shift",       "mnemonic": "SLL",   "syntax": "SLL rd, rs1, rs2",    "description": "rd = rs1 << rs2[4:0]",              "example": "SLL x3, x1, x2"},
        {"category": "Shift",       "mnemonic": "SRL",   "syntax": "SRL rd, rs1, rs2",    "description": "rd = rs1 >> rs2[4:0] (logical)",    "example": "SRL x3, x1, x2"},
        {"category": "Shift",       "mnemonic": "SRA",   "syntax": "SRA rd, rs1, rs2",    "description": "rd = rs1 >> rs2[4:0] (arithmetic)", "example": "SRA x3, x1, x2"},

        # ── Immediate ALU (I-type) ──────────────────────────────────
        {"category": "Immediate",   "mnemonic": "ADDI",  "syntax": "ADDI rd, rs1, imm",   "description": "rd = rs1 + sign_extend(imm12)",     "example": "ADDI x1, x0, 5"},
        {"category": "Immediate",   "mnemonic": "ANDI",  "syntax": "ANDI rd, rs1, imm",   "description": "rd = rs1 & sign_extend(imm12)",     "example": "ANDI x3, x1, 0xFF"},
        {"category": "Immediate",   "mnemonic": "ORI",   "syntax": "ORI rd, rs1, imm",    "description": "rd = rs1 | sign_extend(imm12)",     "example": "ORI x3, x1, 0x0F"},
        {"category": "Immediate",   "mnemonic": "XORI",  "syntax": "XORI rd, rs1, imm",   "description": "rd = rs1 ^ sign_extend(imm12)",     "example": "XORI x3, x1, -1"},
        {"category": "Immediate",   "mnemonic": "SLTI",  "syntax": "SLTI rd, rs1, imm",   "description": "rd = (rs1 < imm) ? 1 : 0 (signed)", "example": "SLTI x3, x1, 10"},
        {"category": "Immediate",   "mnemonic": "SLTIU", "syntax": "SLTIU rd, rs1, imm",  "description": "rd = (rs1 < imm) ? 1 : 0 (unsigned)", "example": "SLTIU x3, x1, 10"},
        {"category": "Immediate",   "mnemonic": "SLLI",  "syntax": "SLLI rd, rs1, shamt", "description": "rd = rs1 << shamt",                 "example": "SLLI x3, x1, 2"},
        {"category": "Immediate",   "mnemonic": "SRLI",  "syntax": "SRLI rd, rs1, shamt", "description": "rd = rs1 >> shamt (logical)",       "example": "SRLI x3, x1, 2"},
        {"category": "Immediate",   "mnemonic": "SRAI",  "syntax": "SRAI rd, rs1, shamt", "description": "rd = rs1 >> shamt (arithmetic)",    "example": "SRAI x3, x1, 2"},

        # ── Upper Immediate ─────────────────────────────────────────
        {"category": "Upper Imm",   "mnemonic": "LUI",   "syntax": "LUI rd, imm20",       "description": "rd = imm20 << 12",                  "example": "LUI x1, 0x12345"},
        {"category": "Upper Imm",   "mnemonic": "AUIPC", "syntax": "AUIPC rd, imm20",     "description": "rd = PC + (imm20 << 12)",           "example": "AUIPC x1, 0x1000"},

        # ── Load / Store ────────────────────────────────────────────
        {"category": "Memory",      "mnemonic": "LW",    "syntax": "LW rd, offset(rs1)",  "description": "rd = Mem[rs1 + offset]",            "example": "LW x5, 0(x0)"},
        {"category": "Memory",      "mnemonic": "SW",    "syntax": "SW rs2, offset(rs1)", "description": "Mem[rs1 + offset] = rs2",           "example": "SW x3, 0(x0)"},

        # ── Branch ──────────────────────────────────────────────────
        {"category": "Branch",      "mnemonic": "BEQ",   "syntax": "BEQ rs1, rs2, label", "description": "if (rs1 == rs2) PC += offset",      "example": "BEQ x1, x2, loop"},
        {"category": "Branch",      "mnemonic": "BNE",   "syntax": "BNE rs1, rs2, label", "description": "if (rs1 != rs2) PC += offset",      "example": "BNE x1, x2, loop"},
        {"category": "Branch",      "mnemonic": "BLT",   "syntax": "BLT rs1, rs2, label", "description": "if (rs1 < rs2) PC += offset (signed)", "example": "BLT x1, x2, loop"},
        {"category": "Branch",      "mnemonic": "BGE",   "syntax": "BGE rs1, rs2, label", "description": "if (rs1 >= rs2) PC += offset (signed)", "example": "BGE x1, x2, loop"},
        {"category": "Branch",      "mnemonic": "BLTU",  "syntax": "BLTU rs1, rs2, label","description": "if (rs1 < rs2) PC += offset (unsigned)", "example": "BLTU x1, x2, loop"},
        {"category": "Branch",      "mnemonic": "BGEU",  "syntax": "BGEU rs1, rs2, label","description": "if (rs1 >= rs2) PC += offset (unsigned)", "example": "BGEU x1, x2, loop"},

        # ── Jump ────────────────────────────────────────────────────
        {"category": "Jump",        "mnemonic": "JAL",   "syntax": "JAL rd, label",       "description": "rd = PC+4; PC += offset",           "example": "JAL x1, func"},
        {"category": "Jump",        "mnemonic": "JALR",  "syntax": "JALR rd, rs1, imm",   "description": "rd = PC+4; PC = rs1 + imm",        "example": "JALR x0, x1, 0"},
    ]


def _arm_cheatsheet() -> list[dict]:
    return [
        # ── Data Processing (Register) ─────────────────────────────
        {"category": "Arithmetic",  "mnemonic": "ADD",   "syntax": "ADD Xd, Xn, Xm",     "description": "Xd = Xn + Xm",                     "example": "ADD X3, X1, X2"},
        {"category": "Arithmetic",  "mnemonic": "SUB",   "syntax": "SUB Xd, Xn, Xm",     "description": "Xd = Xn - Xm",                     "example": "SUB X4, X1, X2"},
        {"category": "Arithmetic",  "mnemonic": "SUBS",  "syntax": "SUBS Xd, Xn, Xm",    "description": "Xd = Xn - Xm; set flags",          "example": "SUBS X4, X1, X2"},
        {"category": "Arithmetic",  "mnemonic": "CMP",   "syntax": "CMP Xn, Xm",          "description": "Xn - Xm; set flags (discard result)", "example": "CMP X1, X2"},

        # ── Data Processing (Logical Register) ─────────────────────
        {"category": "Logical",     "mnemonic": "AND",   "syntax": "AND Xd, Xn, Xm",     "description": "Xd = Xn & Xm",                     "example": "AND X3, X1, X2"},
        {"category": "Logical",     "mnemonic": "ORR",   "syntax": "ORR Xd, Xn, Xm",     "description": "Xd = Xn | Xm",                     "example": "ORR X4, X1, X2"},
        {"category": "Logical",     "mnemonic": "EOR",   "syntax": "EOR Xd, Xn, Xm",     "description": "Xd = Xn ^ Xm",                     "example": "EOR X5, X1, X2"},

        # ── Data Processing (Immediate) ────────────────────────────
        {"category": "Immediate",   "mnemonic": "ADD",   "syntax": "ADD Xd, Xn, #imm12",  "description": "Xd = Xn + imm12",                  "example": "ADD X2, X1, #5"},
        {"category": "Immediate",   "mnemonic": "SUB",   "syntax": "SUB Xd, Xn, #imm12",  "description": "Xd = Xn - imm12",                  "example": "SUB X2, X1, #3"},

        # ── Move ────────────────────────────────────────────────────
        {"category": "Move",        "mnemonic": "MOVZ",  "syntax": "MOVZ Xd, #imm16",     "description": "Xd = imm16 (zero-extend)",          "example": "MOVZ X1, #10"},
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV Xd, #imm16",      "description": "Alias for MOVZ",                    "example": "MOV X1, #42"},

        # ── Load / Store ────────────────────────────────────────────
        {"category": "Memory",      "mnemonic": "LDR",   "syntax": "LDR Xt, [Xn, #off]",  "description": "Xt = Mem[Xn + off]",               "example": "LDR X5, [X0, #0]"},
        {"category": "Memory",      "mnemonic": "STR",   "syntax": "STR Xt, [Xn, #off]",  "description": "Mem[Xn + off] = Xt",               "example": "STR X3, [X0, #0]"},

        # ── Branch ──────────────────────────────────────────────────
        {"category": "Branch",      "mnemonic": "B",     "syntax": "B label",              "description": "PC = PC + offset",                  "example": "B loop"},
        {"category": "Branch",      "mnemonic": "BL",    "syntax": "BL label",             "description": "X30 = PC+4; PC = PC + offset",     "example": "BL func"},
        {"category": "Branch",      "mnemonic": "B.EQ",  "syntax": "B.EQ label",           "description": "Branch if equal (Z=1)",             "example": "B.EQ done"},
        {"category": "Branch",      "mnemonic": "B.NE",  "syntax": "B.NE label",           "description": "Branch if not equal (Z=0)",         "example": "B.NE loop"},
        {"category": "Branch",      "mnemonic": "B.LT",  "syntax": "B.LT label",           "description": "Branch if less than (N!=V)",        "example": "B.LT neg"},
        {"category": "Branch",      "mnemonic": "B.GE",  "syntax": "B.GE label",           "description": "Branch if greater/equal (N==V)",    "example": "B.GE pos"},
        {"category": "Branch",      "mnemonic": "B.GT",  "syntax": "B.GT label",           "description": "Branch if greater (Z=0, N==V)",     "example": "B.GT big"},
        {"category": "Branch",      "mnemonic": "B.LE",  "syntax": "B.LE label",           "description": "Branch if less/equal (Z=1 or N!=V)", "example": "B.LE small"},
        {"category": "Branch",      "mnemonic": "CBZ",   "syntax": "CBZ Xt, label",        "description": "Branch if Xt == 0",                 "example": "CBZ X1, done"},
        {"category": "Branch",      "mnemonic": "CBNZ",  "syntax": "CBNZ Xt, label",       "description": "Branch if Xt != 0",                 "example": "CBNZ X1, loop"},

        # ── Misc ────────────────────────────────────────────────────
        {"category": "Misc",        "mnemonic": "RET",   "syntax": "RET {Xn}",             "description": "PC = Xn (default X30)",             "example": "RET"},
        {"category": "Misc",        "mnemonic": "NOP",   "syntax": "NOP",                  "description": "No operation",                      "example": "NOP"},
    ]


def _x86_cheatsheet() -> list[dict]:
    return [
        # ── Data Movement ───────────────────────────────────────────
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV r32, imm32",       "description": "r32 = imm32",                       "example": "MOV EAX, 42"},
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV r32, r32",          "description": "dst = src",                         "example": "MOV EDX, EAX"},
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV r32, [r32]",        "description": "r32 = Mem[base]",                   "example": "MOV EAX, [EBX]"},
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV [r32], r32",        "description": "Mem[base] = r32",                   "example": "MOV [EBX], EAX"},
        {"category": "Move",        "mnemonic": "MOV",   "syntax": "MOV r32, [r32+disp8]",  "description": "r32 = Mem[base + disp8]",           "example": "MOV EAX, [EBX+4]"},

        # ── Arithmetic ──────────────────────────────────────────────
        {"category": "Arithmetic",  "mnemonic": "ADD",   "syntax": "ADD r32, r32",          "description": "dst += src; set flags",             "example": "ADD EAX, ECX"},
        {"category": "Arithmetic",  "mnemonic": "ADD",   "syntax": "ADD r32, imm8",         "description": "dst += imm8; set flags",            "example": "ADD EAX, 5"},
        {"category": "Arithmetic",  "mnemonic": "SUB",   "syntax": "SUB r32, r32",          "description": "dst -= src; set flags",             "example": "SUB EAX, ECX"},
        {"category": "Arithmetic",  "mnemonic": "SUB",   "syntax": "SUB r32, imm8",         "description": "dst -= imm8; set flags",            "example": "SUB EAX, 3"},
        {"category": "Arithmetic",  "mnemonic": "CMP",   "syntax": "CMP r32, r32",          "description": "dst - src; set flags (no store)",   "example": "CMP EAX, ECX"},
        {"category": "Arithmetic",  "mnemonic": "CMP",   "syntax": "CMP r32, imm8",         "description": "dst - imm8; set flags (no store)",  "example": "CMP EAX, 5"},

        # ── Logical ─────────────────────────────────────────────────
        {"category": "Logical",     "mnemonic": "AND",   "syntax": "AND r32, r32",          "description": "dst &= src; set flags",             "example": "AND EAX, ECX"},
        {"category": "Logical",     "mnemonic": "AND",   "syntax": "AND r32, imm8",         "description": "dst &= imm8; set flags",            "example": "AND EAX, 0x0F"},
        {"category": "Logical",     "mnemonic": "OR",    "syntax": "OR r32, r32",           "description": "dst |= src; set flags",             "example": "OR EAX, ECX"},
        {"category": "Logical",     "mnemonic": "OR",    "syntax": "OR r32, imm8",          "description": "dst |= imm8; set flags",            "example": "OR EAX, 0x0F"},
        {"category": "Logical",     "mnemonic": "XOR",   "syntax": "XOR r32, r32",          "description": "dst ^= src; set flags",             "example": "XOR EAX, ECX"},
        {"category": "Logical",     "mnemonic": "XOR",   "syntax": "XOR r32, imm8",         "description": "dst ^= imm8; set flags",            "example": "XOR EAX, 0xFF"},

        # ── Control Flow ────────────────────────────────────────────
        {"category": "Control",     "mnemonic": "JMP",   "syntax": "JMP label",             "description": "Unconditional jump",                "example": "JMP loop"},
        {"category": "Control",     "mnemonic": "JE",    "syntax": "JE label",              "description": "Jump if equal (ZF=1)",              "example": "JE done"},
        {"category": "Control",     "mnemonic": "JNE",   "syntax": "JNE label",             "description": "Jump if not equal (ZF=0)",          "example": "JNE loop"},
        {"category": "Control",     "mnemonic": "JL",    "syntax": "JL label",              "description": "Jump if less (SF!=OF)",             "example": "JL neg"},
        {"category": "Control",     "mnemonic": "JGE",   "syntax": "JGE label",             "description": "Jump if greater/equal (SF==OF)",    "example": "JGE pos"},
        {"category": "Control",     "mnemonic": "JLE",   "syntax": "JLE label",             "description": "Jump if less/equal",                "example": "JLE small"},
        {"category": "Control",     "mnemonic": "JG",    "syntax": "JG label",              "description": "Jump if greater",                   "example": "JG big"},
        {"category": "Control",     "mnemonic": "CALL",  "syntax": "CALL label",            "description": "Push return addr; jump to label",   "example": "CALL func"},
        {"category": "Control",     "mnemonic": "RET",   "syntax": "RET",                   "description": "Pop return addr; jump to it",       "example": "RET"},

        # ── Stack ───────────────────────────────────────────────────
        {"category": "Stack",       "mnemonic": "PUSH",  "syntax": "PUSH r32",              "description": "ESP -= 4; Mem[ESP] = r32",          "example": "PUSH EAX"},
        {"category": "Stack",       "mnemonic": "POP",   "syntax": "POP r32",               "description": "r32 = Mem[ESP]; ESP += 4",          "example": "POP EAX"},

        # ── Misc ────────────────────────────────────────────────────
        {"category": "Misc",        "mnemonic": "NOP",   "syntax": "NOP",                   "description": "No operation",                      "example": "NOP"},
    ]
