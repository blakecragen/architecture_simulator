"""
Tests for the standalone backend simulator harness (sim/harness.py).

This is the canonical, UI-independent entry point to the simulator. The harness
builds a CPU for any (isa, model) preset, runs a program, and returns a SimResult
with convenient accessors for registers / data memory / the PC stream.

These tests verify, with no Flask/UI involvement:
  * the preset / predictor / isa / model registries are exactly as expected,
  * every program source (asm text, int list, hex strings, demo) runs,
  * representative programs compute the RIGHT answers across all five models
    and all three ISAs, checked via SimResult.reg(...) / .mem_at(...),
  * harness parameters (predictor, lanes, prediction stage) thread through,
  * SimResult accessors agree with each other,
  * bad inputs raise HarnessError (and bad assembly raises *something*),
  * the CLI (main / python3 -m sim.harness) returns the right exit codes and
    emits valid JSON.

Run from repo root:  python3 -m pytest tests/ -q
"""
import contextlib
import io
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import (
    PREDICTOR_CLASSES,
    PREDICTORS,
    PRESETS,
    ISA_CONFIGS,
    ISAS,
    MODELS,
    HarnessError,
    SimResult,
    assemble,
    build_cpu,
    main,
    parse_program,
    resolve_preset,
    simulate,
)


# ── small helpers ───────────────────────────────────────────────────────────
ALL_MODELS = ("single_cycle", "multicycle", "pipeline", "ooo", "superscalar")
# Cycle budgets generous enough for OoO/superscalar to drain in-order commits.
CYCLES = {
    "single_cycle": 20,
    "multicycle": 60,
    "pipeline": 30,
    "ooo": 60,
    "superscalar": 40,
}


def _capture_stdout(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


def _capture_stderr(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


# ============================================================================
# 1. REGISTRIES
# ============================================================================
class TestRegistries:
    EXPECTED_PRESET_LABELS = {
        "riscv/single_cycle": "RISC-V Single Cycle",
        "riscv/multicycle": "RISC-V FetDecExe",
        "riscv/configurable": "RISC-V Configurable",
        "riscv/pipeline": "RISC-V Pipeline",
        "riscv/ooo": "RISC-V Out-of-Order",
        "riscv/superscalar": "RISC-V Superscalar",
        "arm/single_cycle": "ARM Single Cycle",
        "arm/multicycle": "ARM FetDecExe",
        "arm/configurable": "ARM Configurable",
        "arm/pipeline": "ARM Pipeline",
        "arm/ooo": "ARM Out-of-Order",
        "arm/superscalar": "ARM Superscalar",
        "x86/single_cycle": "x86 Single Cycle",
        "x86/multicycle": "x86 FetDecExe",
        "x86/configurable": "x86 Configurable",
        "x86/pipeline": "x86 Pipeline",
        "x86/ooo": "x86 Out-of-Order",
        "x86/superscalar": "x86 Superscalar",
    }

    def test_presets_has_exactly_18_keys(self):
        # 3 ISAs x 6 models (single_cycle, multicycle, configurable, pipeline,
        # ooo, superscalar).
        assert len(PRESETS) == 18

    def test_presets_keys_are_three_isa_by_six_models(self):
        assert set(PRESETS) == set(self.EXPECTED_PRESET_LABELS)

    def test_presets_labels_match_expected(self):
        for key, label in self.EXPECTED_PRESET_LABELS.items():
            assert PRESETS[key]["label"] == label

    def test_riscv_multicycle_label_is_fetdecexe(self):
        assert PRESETS["riscv/multicycle"]["label"] == "RISC-V FetDecExe"

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRESET_LABELS))
    def test_every_preset_build_is_callable(self, key):
        assert callable(PRESETS[key]["build"])

    @pytest.mark.parametrize("key", sorted(EXPECTED_PRESET_LABELS))
    def test_every_preset_isa_and_model_fields_match_key(self, key):
        isa, model = key.split("/")
        assert PRESETS[key]["isa"] == isa
        assert PRESETS[key]["model"] == model

    def test_predictor_classes_has_six_known_predictors(self):
        assert set(PREDICTOR_CLASSES) == {
            "always_taken", "bimodal", "btb",
            "gshare", "never_taken", "no_prediction",
        }

    def test_predictors_tuple_is_sorted(self):
        assert PREDICTORS == (
            "always_taken", "bimodal", "btb",
            "gshare", "never_taken", "no_prediction",
        )

    @pytest.mark.parametrize("name", sorted(PREDICTOR_CLASSES))
    def test_every_predictor_class_is_instantiable(self, name):
        inst = PREDICTOR_CLASSES[name](prediction_stage="id")
        assert inst.name == name

    def test_isas_tuple_is_correct(self):
        assert ISAS == ("riscv", "arm", "x86")

    def test_models_tuple_is_correct(self):
        assert MODELS == ("single_cycle", "multicycle", "configurable",
                          "pipeline", "ooo", "superscalar")

    def test_isa_configs_has_three_isas(self):
        assert set(ISA_CONFIGS) == {"riscv", "arm", "x86"}


# ============================================================================
# 2. PROGRAM SOURCES
# ============================================================================
class TestProgramSources:
    def test_simulate_with_asm_assembles_and_runs(self):
        r = simulate("riscv", "single_cycle", asm="ADDI x1,x0,5\nADDI x2,x1,3", cycles=10)
        assert r.reg("x2") == 8

    def test_simulate_with_program_ints_runs(self):
        # ADDI x1,x0,5 ; ADDI x2,x1,3
        r = simulate("riscv", "single_cycle", program=[0x00500093, 0x00308113], cycles=10)
        assert r.reg("x2") == 8

    def test_simulate_with_program_hex_strings_runs(self):
        r = simulate("riscv", "single_cycle", program=["0x00500093", "0x00308113"], cycles=10)
        assert r.reg("x2") == 8

    def test_simulate_with_no_source_uses_demo_program(self):
        r = simulate("riscv", "single_cycle", cycles=60)
        # demo is the fibonacci loop; program must be non-empty and match the demo.
        assert list(r.program) == list(ISA_CONFIGS["riscv"].demo_program())

    def test_simulate_demo_program_produces_nonzero_registers(self):
        r = simulate("riscv", "single_cycle", cycles=80)
        assert any(r.reg(n) for n in r.reg_names)

    def test_program_format_words_for_riscv(self):
        r = simulate("riscv", "single_cycle", asm="ADDI x1,x0,1", cycles=5)
        assert r.program_format == "words"

    def test_program_format_words_for_arm(self):
        r = simulate("arm", "single_cycle", asm="MOVZ X1, #1", cycles=5)
        assert r.program_format == "words"

    def test_program_format_bytes_for_x86(self):
        r = simulate("x86", "single_cycle", asm="MOV EAX, 1", cycles=5)
        assert r.program_format == "bytes"


# ============================================================================
# 3. CORRECTNESS VIA SimResult  (the key value)
# ============================================================================
class TestRiscvCorrectness:
    @pytest.mark.parametrize("model", ALL_MODELS)
    def test_alu_chain_x2_equals_8_across_all_models(self, model):
        r = simulate("riscv", model, asm="ADDI x1,x0,5\nADDI x2,x1,3", cycles=CYCLES[model])
        assert r.reg("x2") == 8

    @pytest.mark.parametrize("model", ["single_cycle", "multicycle", "pipeline"])
    def test_store_then_load_same_address(self, model):
        # SW x1,0(x0) then LW x2 back. In-order models read it back directly.
        asm = (
            "ADDI x1,x0,42\n"
            "SW   x1,0(x0)\n"
            "ADDI x0,x0,0\n"
            "ADDI x0,x0,0\n"
            "LW   x2,0(x0)\n"
        )
        r = simulate("riscv", model, asm=asm, cycles=CYCLES[model])
        assert r.mem_at(0x0) == 42
        assert r.reg("x2") == 42

    def test_ooo_store_to_memory_commits(self):
        # OoO has no load-store disambiguation; store to several distinct
        # addresses and read memory directly (loads of *other* addresses are
        # independent, so they read the committed values).
        asm = (
            "ADDI x1,x0,42\n"
            "ADDI x2,x0,99\n"
            "SW   x1,0(x0)\n"
            "SW   x2,4(x0)\n"
            "ADDI x7,x0,8\n"
            "SW   x1,0(x7)\n"
            "SW   x2,4(x7)\n"
            "LW   x3,0(x0)\n"
            "LW   x4,4(x0)\n"
            "LW   x5,0(x7)\n"
            "LW   x6,4(x7)\n"
        )
        r = simulate("riscv", "ooo", asm=asm, cycles=80)
        assert r.mem_at(0x0) == 42
        assert r.mem_at(0x4) == 99
        assert r.mem_at(0x8) == 42
        assert r.mem_at(0xC) == 99
        # Loads to addresses distinct from earlier in-flight stores are safe.
        assert r.reg("x3") == 42
        assert r.reg("x4") == 99
        assert r.reg("x5") == 42
        assert r.reg("x6") == 99

    def test_nonzero_memory_keys_are_byte_addresses(self):
        asm = (
            "ADDI x1,x0,42\n"
            "ADDI x2,x0,99\n"
            "SW   x1,0(x0)\n"
            "SW   x2,4(x0)\n"
        )
        r = simulate("riscv", "single_cycle", asm=asm, cycles=10)
        nz = r.nonzero_memory()
        assert nz[0] == 42
        assert nz[4] == 99

    def test_auipc_pc_relative_on_ooo(self):
        # Regression guard: AUIPC x5, 1 at PC=4 -> x5 = 4 + (1<<12) = 4100.
        r = simulate("riscv", "ooo", asm="ADDI x1,x0,0\nAUIPC x5,1", cycles=40)
        assert r.reg("x5") == 4100

    def test_auipc_pc_relative_on_single_cycle(self):
        r = simulate("riscv", "single_cycle", asm="ADDI x1,x0,0\nAUIPC x5,1", cycles=10)
        assert r.reg("x5") == 4100


class TestArmCorrectness:
    @pytest.mark.parametrize("model", ALL_MODELS)
    def test_movz_add_compute(self, model):
        # MOVZ X1,#7 ; MOVZ X2,#5 ; ADD X3,X1,X2 -> X3 = 12
        asm = "MOVZ X1, #7\nMOVZ X2, #5\nADD X3, X1, X2"
        r = simulate("arm", model, asm=asm, cycles=CYCLES[model])
        assert r.reg("X1") == 7
        assert r.reg("X2") == 5
        assert r.reg("X3") == 12

    def test_arm_xzr_register_reads_zero(self):
        # X31 is XZR and always reads as zero.
        r = simulate("arm", "single_cycle", asm="MOVZ X1, #7", cycles=5)
        assert r.reg("XZR") == 0
        assert r.reg(31) == 0


class TestX86Correctness:
    # NOTE: x86 multicycle/pipeline are intentionally excluded here — they have a
    # real every-other-instruction fetch bug (see TestX86PipelineMulticycleBug).
    @pytest.mark.parametrize("model", ["single_cycle", "ooo"])
    def test_mov_add_compute(self, model):
        # MOV EAX,7 ; MOV EBX,5 ; ADD EAX,EBX -> EAX = 12 (x86 is byte-format)
        asm = "MOV EAX, 7\nMOV EBX, 5\nADD EAX, EBX"
        r = simulate("x86", model, asm=asm, cycles=CYCLES[model])
        assert r.reg("EAX") == 12
        assert r.reg("EBX") == 5

    def test_x86_program_is_byte_format(self):
        r = simulate("x86", "single_cycle", asm="MOV EAX, 7", cycles=5)
        assert r.program_format == "bytes"
        # MOV EAX, imm32 is opcode 0xB8 + 4 imm bytes = 5 bytes.
        assert r.program[0] == 0xB8
        assert len(r.program) == 5


class TestX86VariableLengthFetch:
    """Regression guard for two x86 multicycle/pipeline bugs (now fixed).

    1. INSTRUCTION DROPPING — X86Fetch advances the PC by the instruction
       length, but x86 is variable-length and the real decoder sits a stage
       downstream of fetch, so fetch used the *previous* instruction's length
       and landed mid-instruction; every other instruction was skipped. Fixed
       with a fetch-stage length predecode (a length-only X86Decoder reading
       imem directly) in the x86 pipeline + multicycle presets.
    2. EAX NEVER FORWARDED — the shared ForwardingUnit hardcoded the RISC-V
       "register 0 is the zero register, never forward it" rule, but x86 has no
       zero register and EAX is index 0. Fixed by parameterizing the unit's
       zero-register index (x86 = none, ARM = 31, RISC-V = 0).
    """

    @pytest.mark.parametrize("model", ["multicycle", "pipeline"])
    def test_consecutive_movs_both_commit(self, model):
        r = simulate("x86", model, asm="MOV EAX, 7\nMOV EBX, 5", cycles=CYCLES[model])
        assert r.reg("EAX") == 7
        assert r.reg("EBX") == 5

    @pytest.mark.parametrize("model", ["multicycle", "pipeline"])
    def test_mov_add_compute_equals_12(self, model):
        asm = "MOV EAX, 7\nMOV EBX, 5\nADD EAX, EBX"
        r = simulate("x86", model, asm=asm, cycles=CYCLES[model])
        assert r.reg("EAX") == 12

    @pytest.mark.parametrize("model", ["single_cycle", "multicycle", "pipeline"])
    def test_store_reaches_memory(self, model):
        # MOV ECX,40; MOV EAX,99; MOV [ECX],EAX  -> data memory word 10 = 99.
        asm = "MOV ECX, 40\nMOV EAX, 99\nMOV [ECX], EAX\nNOP\nNOP\nNOP\nNOP"
        r = simulate("x86", model, asm=asm, cycles=CYCLES[model])
        assert r.mem_at(40) == 99


# ============================================================================
# 4. PARAMETERS
# ============================================================================
class TestParameters:
    @pytest.mark.parametrize("predictor", PREDICTORS)
    def test_predictor_threads_through_pipeline(self, predictor):
        r = simulate("riscv", "pipeline", asm="ADDI x1,x0,5\nADDI x2,x1,3",
                     cycles=30, branch_predictor=predictor)
        assert r.reg("x2") == 8

    @pytest.mark.parametrize("predictor", PREDICTORS)
    def test_predictor_threads_through_ooo(self, predictor):
        r = simulate("riscv", "ooo", asm="ADDI x1,x0,5\nADDI x2,x1,3",
                     cycles=60, branch_predictor=predictor)
        assert r.reg("x2") == 8

    @pytest.mark.parametrize("num_lanes", [1, 2, 3, 4])
    def test_superscalar_lanes_agree_with_single_cycle(self, num_lanes):
        straight = "ADDI x1,x0,1\nADDI x2,x0,2\nADDI x3,x0,3\nADDI x4,x0,4"
        base = simulate("riscv", "single_cycle", asm=straight, cycles=10)
        r = simulate("riscv", "superscalar", asm=straight, cycles=40, num_lanes=num_lanes)
        for n in ("x1", "x2", "x3", "x4"):
            assert r.reg(n) == base.reg(n)

    @pytest.mark.parametrize("stage", ["id", "if"])
    def test_prediction_stage_runs_on_pipeline(self, stage):
        r = simulate("riscv", "pipeline", asm="ADDI x1,x0,5\nADDI x2,x1,3",
                     cycles=30, branch_predictor="gshare", prediction_stage=stage)
        assert r.reg("x2") == 8

    def test_build_cpu_with_predictor_instance(self):
        # branch_predictor may be a ready instance, not just a name.
        inst = PREDICTOR_CLASSES["gshare"](prediction_stage="id")
        cpu = build_cpu("riscv/pipeline", parse_program([0x00500093]), branch_predictor=inst)
        assert cpu is not None

    def test_build_cpu_returns_cpu_without_running(self):
        from sim.component.wire import CPU
        cpu = build_cpu("riscv/single_cycle", [0x00500093])
        assert isinstance(cpu, CPU)


# ============================================================================
# 5. SimResult ACCESSORS
# ============================================================================
class TestSimResultAccessors:
    def _riscv_result(self):
        # ADDI x2,x0,9  -> x2 (== ABI 'sp') == 9
        return simulate("riscv", "single_cycle", asm="ADDI x2,x0,9", cycles=5)

    def test_reg_by_index_abi_name_and_alias_agree(self):
        r = self._riscv_result()
        assert r.reg(2) == 9
        assert r.reg("sp") == 9   # ABI name for x2
        assert r.reg("x2") == 9   # numbered alias

    def test_reg_unknown_name_raises(self):
        r = self._riscv_result()
        with pytest.raises(HarnessError):
            r.reg("not_a_reg")

    def test_x86_reg_by_index_and_abi_and_alias_agree(self):
        r = simulate("x86", "single_cycle", asm="MOV EAX, 12", cycles=5)
        assert r.reg(0) == 12
        assert r.reg("EAX") == 12
        assert r.reg("e0") == 12

    def test_registers_property_returns_list(self):
        r = self._riscv_result()
        regs = r.registers
        assert isinstance(regs, list)
        assert regs[2] == 9

    def test_mem_at_equals_mem_word(self):
        asm = "ADDI x1,x0,42\nSW x1,0(x0)\nSW x1,4(x0)"
        r = simulate("riscv", "single_cycle", asm=asm, cycles=10)
        assert r.mem_at(0x0) == r.mem_word(0x0 >> 2)
        assert r.mem_at(0x4) == r.mem_word(0x4 >> 2)

    def test_nonzero_memory_returns_dict_of_byte_addr_to_value(self):
        asm = "ADDI x1,x0,7\nSW x1,8(x0)"
        r = simulate("riscv", "single_cycle", asm=asm, cycles=10)
        nz = r.nonzero_memory()
        assert isinstance(nz, dict)
        assert nz == {8: 7}

    def test_pc_stream_length_about_cycles(self):
        # include_reset adds the cycle-0 snapshot, so length == cycles + 1.
        r = simulate("riscv", "single_cycle", asm="ADDI x1,x0,1", cycles=5)
        assert len(r.pc_stream) == 6

    def test_pc_stream_entries_are_hex_strings(self):
        r = simulate("riscv", "single_cycle", asm="ADDI x1,x0,1", cycles=5)
        assert all(isinstance(pc, str) and pc.startswith("0x") for pc in r.pc_stream)

    def test_summary_shape(self):
        r = self._riscv_result()
        s = r.summary()
        assert set(s) == {
            "preset", "isa", "model", "cycles",
            "program_words", "nonzero_registers", "nonzero_memory",
        }
        assert s["preset"] == "riscv/single_cycle"
        assert s["isa"] == "riscv"
        assert s["model"] == "single_cycle"
        assert s["nonzero_registers"]["sp"] == 9

    def test_simresult_metadata_fields(self):
        r = self._riscv_result()
        assert r.preset == "riscv/single_cycle"
        assert r.isa == "riscv"
        assert r.model == "single_cycle"
        assert r.cpu is not None
        assert r.reg_names == ISA_CONFIGS["riscv"].register_names()
        assert isinstance(r.cycles, list) and len(r.cycles) > 0

    def test_simresult_is_dataclass_instance(self):
        r = self._riscv_result()
        assert isinstance(r, SimResult)


# ============================================================================
# 6. ERROR HANDLING
# ============================================================================
class TestErrorHandling:
    def test_unknown_preset_raises_harness_error(self):
        with pytest.raises(HarnessError):
            resolve_preset(preset="foo/bar")

    def test_unknown_preset_via_simulate_raises(self):
        with pytest.raises(HarnessError):
            simulate(preset="nope/nope", cycles=2)

    def test_unknown_isa_in_assemble_raises_harness_error(self):
        with pytest.raises(HarnessError):
            assemble("zzz", "ADDI x1,x0,1")

    def test_parse_program_non_list_raises(self):
        with pytest.raises(HarnessError):
            parse_program("not a list")

    def test_parse_program_non_numeric_entry_raises(self):
        with pytest.raises(HarnessError):
            parse_program(["definitely_not_a_number"])

    def test_simulate_non_list_program_raises(self):
        with pytest.raises(HarnessError):
            simulate("riscv", "single_cycle", program="not a list", cycles=2)

    def test_unknown_predictor_raises_harness_error(self):
        with pytest.raises(HarnessError):
            simulate("riscv", "pipeline", branch_predictor="nope", cycles=2)

    def test_build_cpu_unknown_predictor_raises(self):
        with pytest.raises(HarnessError):
            build_cpu("riscv/pipeline", [0x00500093], branch_predictor="nope")

    def test_missing_isa_model_and_preset_raises(self):
        with pytest.raises(HarnessError):
            resolve_preset()

    def test_isa_only_without_model_raises(self):
        with pytest.raises(HarnessError):
            resolve_preset(isa="riscv")

    def test_bad_assembly_raises_something(self):
        # Assembler error type is fine; assert it raises *something* (it raises
        # AssemblerError, not HarnessError — we do not force a specific type).
        with pytest.raises(Exception):
            assemble("riscv", "THISISNOTANOPCODE x9, x9")

    def test_bad_assembly_via_simulate_propagates(self):
        with pytest.raises(Exception):
            simulate("riscv", "single_cycle", asm="BOGUSOP x1, x2", cycles=2)


# ============================================================================
# 7. CLI
# ============================================================================
class TestCLI:
    def test_list_presets_returns_zero(self):
        rc, out = _capture_stdout(main, ["--list-presets"])
        assert rc == 0
        assert "riscv/single_cycle" in out
        assert "predictors:" in out

    def test_json_run_returns_zero_and_valid_json(self):
        rc, out = _capture_stdout(
            main,
            ["--isa", "riscv", "--model", "single_cycle",
             "--asm-text", "ADDI x1,x0,7", "--cycles", "10", "--json"],
        )
        assert rc == 0
        data = json.loads(out)
        assert set(data) == {
            "preset", "isa", "model", "cycles",
            "program_words", "nonzero_registers", "nonzero_memory",
        }
        assert data["preset"] == "riscv/single_cycle"
        # ADDI x1,x0,7 -> x1 == ABI 'ra' == 7
        assert data["nonzero_registers"]["ra"] == 7

    def test_preset_flag_runs(self):
        rc, out = _capture_stdout(
            main,
            ["--preset", "riscv/pipeline", "--asm-text", "ADDI x1,x0,3",
             "--cycles", "20", "--json"],
        )
        assert rc == 0
        data = json.loads(out)
        assert data["preset"] == "riscv/pipeline"

    def test_text_report_run_returns_zero(self):
        rc, out = _capture_stdout(
            main,
            ["--isa", "riscv", "--model", "single_cycle",
             "--asm-text", "ADDI x1,x0,7", "--cycles", "10"],
        )
        assert rc == 0
        assert "preset" in out
        assert "registers" in out

    def test_demo_run_returns_zero(self):
        rc, out = _capture_stdout(
            main,
            ["--isa", "riscv", "--model", "single_cycle", "--demo",
             "--cycles", "80", "--json"],
        )
        assert rc == 0

    def test_unknown_preset_exit_code_2(self):
        rc, _ = _capture_stderr(main, ["--preset", "foo/bar", "--demo"])
        assert rc == 2

    def test_missing_isa_and_model_exit_code_2(self):
        rc, _ = _capture_stderr(main, ["--asm-text", "ADDI x1,x0,1"])
        assert rc == 2

    def test_asm_file_run_returns_zero(self):
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".s", delete=False) as f:
                f.write("ADDI x1,x0,7\n")
                path = f.name
            rc, out = _capture_stdout(
                main,
                ["--isa", "riscv", "--model", "single_cycle",
                 "--asm", path, "--cycles", "10", "--json"],
            )
            assert rc == 0
            assert json.loads(out)["nonzero_registers"]["ra"] == 7
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_hex_file_run_returns_zero(self):
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".hex", delete=False) as f:
                # ADDI x1,x0,5 ; ADDI x2,x1,3
                f.write("0x00500093 0x00308113\n")
                path = f.name
            rc, out = _capture_stdout(
                main,
                ["--isa", "riscv", "--model", "single_cycle",
                 "--hex", path, "--cycles", "10", "--json"],
            )
            assert rc == 0
            assert json.loads(out)["nonzero_registers"]["sp"] == 8  # x2
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def test_hex_words_csv_run_returns_zero(self):
        rc, out = _capture_stdout(
            main,
            ["--isa", "riscv", "--model", "single_cycle",
             "--hex-words", "0x00500093,0x00308113", "--cycles", "10", "--json"],
        )
        assert rc == 0
        assert json.loads(out)["nonzero_registers"]["sp"] == 8  # x2

    def test_missing_asm_file_exit_code_2(self):
        rc, _ = _capture_stderr(
            main,
            ["--isa", "riscv", "--model", "single_cycle", "--asm", "/no/such/file.s"],
        )
        assert rc == 2

    def test_bad_assembly_via_cli_exit_code_1(self):
        # Assembler failures are surfaced as simulation failures (exit 1),
        # not bad-input (exit 2), because AssemblerError is not HarnessError.
        rc, err = _capture_stderr(
            main,
            ["--isa", "riscv", "--model", "single_cycle",
             "--asm-text", "BOGUSOP x1, x2", "--cycles", "5"],
        )
        assert rc == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
