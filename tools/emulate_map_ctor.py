"""
Determine which of 0x578C60's stack arguments write to which fields of the
per-area "Map" object, by emulating just that one function with controlled
inputs instead of hand-tracing the FPU-interleaved disassembly by eye (which
proved slow and error-prone - see NOTES.md, "Area Map marker fix - Step 1/2
progress").

0x578C60 is the constructor/setup function (traced via tools/disasm_helpers.py)
that writes BOTH the marker-calibration fields (+0x18/+0x1c/+0x20/+0x24, read
only by the Area Map's 0x578E00) and the grid-array fields (+0/+4/+8/+0xc,
read by the HUD's minimap code via 0x579090) on ONE shared per-area object.
Open question: do the 4 ARE-loader pixel-space values (the ones a prior fix
redirected, causing a HUD-minimap regression) feed only the marker fields, or
also the grid fields the HUD depends on?

Approach: run the function once per argument slot with that slot perturbed
and all others at a neutral baseline, and diff the resulting object bytes
against an all-baseline run. Whichever fields change reveal that slot's
dependents - the real, compiled code answers this, no hand-derived
esp-relative offsets or FPU-stack-effect tracing needed.

0x578C60 makes exactly 2 internal calls (confirmed by disasm_helpers.py):
- 0x6fae8c: a self-contained FPU round-to-int helper, no OS calls - let it
  run for real.
- 0x6fa7e6: a small wrapper whose OWN prologue/epilogue does real stack
  cleanup for its 1 pushed arg (via 2 pops before its own `ret`) - we let
  THAT run for real too, and hook only the actually-risky part: the CRT
  allocator it calls into at 0x6fd8cf. Hooking at the deepest safe point
  (rather than stubbing 0x6fa7e6 itself) means we never have to guess at its
  calling convention - only 0x6fd8cf's (a plain `ret`, confirmed by reading
  its caller's cleanup code).

Requires `unicorn` (installed this session specifically for this script).
"""

import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, UC_PROT_ALL
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

IMAGE_BASE = 0x400000
FUNC_VA = 0x578C60
ALLOC_CALL_VA = 0x6FD8CF  # real CRT allocator inside 0x6fa7e6, hooked out
N_ARGS = 12  # 0x578C60 ends in `ret 0x30` = 0x30/4 dwords of stack args
FIELDS = [0x0, 0x4, 0x8, 0xC, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24,
          0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48, 0x4C]
# Extended 2026-08-24 past +0x24: direct disassembly of the ARE-loader call
# site (VA 0x509F01-0x509F37, function ~0x508Cxx) showed 0x578C60 being
# called with the 4 already-known MapPt1/2*440/256 rounded-int args PLUS the
# 4 raw (unscaled) WorldPt1X/Y, WorldPt2X/Y floats read straight from the
# .ARE GFF's Map struct - only 9 of the 12 stack slots had been mapped to a
# field by the original +0x24-bounded run, so the object almost certainly
# has fields beyond +0x24 nobody had looked at. See NOTES.md.

SCRATCH_BASE = 0x08000000
SCRATCH_SIZE = 0x00200000
OBJ_ADDR = SCRATCH_BASE + 0x1000
OBJ_SIZE = 0x200
ALLOC_ADDR = SCRATCH_BASE + 0x10000
ALLOC_SIZE = 0x10000
STACK_TOP = SCRATCH_BASE + 0x180000
STOP_ADDR = SCRATCH_BASE  # first scratch page; never actually executed


def load_exe(path):
    with open(path, "rb") as f:
        return f.read()


def make_uc(exe_bytes):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image_size = (len(exe_bytes) + 0xFFF) & ~0xFFF
    uc.mem_map(IMAGE_BASE, image_size, UC_PROT_ALL)
    uc.mem_write(IMAGE_BASE, exe_bytes)
    uc.mem_map(SCRATCH_BASE, SCRATCH_SIZE, UC_PROT_ALL)
    return uc


def hook_alloc(uc, address, size, user_data):
    # Fake the CRT allocator: return ALLOC_ADDR, then do exactly what a bare
    # `ret` does (0x6fd8cf's caller cleans up its own pushed arg itself).
    uc.reg_write(UC_X86_REG_EAX, ALLOC_ADDR)
    esp = uc.reg_read(UC_X86_REG_ESP)
    (ret_addr,) = struct.unpack("<I", uc.mem_read(esp, 4))
    uc.reg_write(UC_X86_REG_ESP, esp + 4)
    uc.reg_write(UC_X86_REG_EIP, ret_addr)
    uc.emu_stop()


def run_once(exe_bytes, arg_values):
    assert len(arg_values) == N_ARGS
    uc = make_uc(exe_bytes)
    uc.mem_write(OBJ_ADDR, b"\x00" * OBJ_SIZE)
    uc.mem_write(ALLOC_ADDR, b"\x00" * ALLOC_SIZE)
    uc.hook_add(UC_HOOK_CODE, hook_alloc, begin=ALLOC_CALL_VA, end=ALLOC_CALL_VA)

    layout = struct.pack("<I", STOP_ADDR) + b"".join(struct.pack("<i", v) for v in arg_values)
    uc.mem_write(STACK_TOP, layout)

    uc.reg_write(UC_X86_REG_ESP, STACK_TOP)
    uc.reg_write(UC_X86_REG_ECX, OBJ_ADDR)

    eip = FUNC_VA
    for _ in range(64):  # bounded: one iteration per hook hit, plenty of headroom
        uc.emu_start(eip, STOP_ADDR, count=2_000_000)
        eip = uc.reg_read(UC_X86_REG_EIP)
        if eip == STOP_ADDR:
            break
    else:
        raise RuntimeError("emulation did not reach STOP_ADDR - runaway or unhandled hook")

    return bytes(uc.mem_read(OBJ_ADDR, OBJ_SIZE))


def field_dump(obj_bytes):
    out = {}
    for off in FIELDS:
        (i,) = struct.unpack_from("<i", obj_bytes, off)
        (f,) = struct.unpack_from("<f", obj_bytes, off)
        out[off] = (i, f)
    return out


def main(exe_path):
    exe_bytes = load_exe(exe_path)

    VARIANT = 500

    # Distinct baseline values per slot, not one uniform value: with every
    # slot equal, subtractions like (map1-map2) degenerate to 0/0, which
    # makes perturbing ANY slot look like it affects every field (confirmed
    # - an all-2s baseline showed exactly this false "everything depends on
    # everything" signal). Distinct small primes-ish values keep every
    # subtraction/division non-degenerate so only real dependencies show up.
    baseline_args = [11 + 7 * i for i in range(N_ARGS)]
    baseline_obj = run_once(exe_bytes, baseline_args)
    baseline_fields = field_dump(baseline_obj)

    print("baseline fields (distinct per-slot values, see baseline_args):")
    for off, (i, f) in baseline_fields.items():
        print(f"  +0x{off:02x}: int={i} float={f}")
    print()

    for slot in range(N_ARGS):
        args = list(baseline_args)
        args[slot] = VARIANT
        variant_obj = run_once(exe_bytes, args)
        variant_fields = field_dump(variant_obj)

        changed = [off for off in FIELDS if variant_fields[off] != baseline_fields[off]]
        changed_str = ", ".join(f"+0x{off:02x}" for off in changed) if changed else "(none)"
        entry_offset = 4 + 4 * slot
        print(f"slot {slot:2d} (stack offset +0x{entry_offset:02x} at entry) perturbed -> fields changed: {changed_str}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../backups/swkotor.exe.pre-markerfix-backup")
