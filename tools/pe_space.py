"""Reserve space in swkotor.exe for a note table too big for the .text cave.

WHY THIS EXISTS
---------------
The note-correction table lives in the zero tail of .text at 0x73C270. That
tail is 3485 bytes and it is the ONLY run of free space >= 600 B anywhere in
.text (measured, 2026-08-29), so at 16 B/entry the cave caps out at ~209
corrections once the match routine has taken its ~128 B. The reviewed table is
250 entries = 4000 B and does not fit.

WHY NOT A NEW SECTION
---------------------
The obvious fix is a 5th PE section. Section headers must be a contiguous
array, so a new header would land at file offset 0xAA8..0xACF - and 0xAC0
holds a 16-byte "Hellspawn Reborn" watermark left by a third-party patcher
(it is absent from the pristine Steam exe). Adding a section would destroy
another tool's marker, and that tool may read it to decide whether the exe is
already patched.

WHAT THIS DOES INSTEAD
----------------------
Grows the LAST section (.rsrc) by REGION_BYTES, which needs three header
fields changed and no new header:

    .rsrc SizeOfRawData   += REGION_BYTES
    .rsrc VirtualSize      = (aligned old end) + REGION_BYTES
    OptionalHeader.SizeOfImage += REGION_BYTES

and appends REGION_BYTES of zeros at the end of the file, which is exactly
where .rsrc's raw data already ends. The region is read-only initialised data,
which is all the table needs - the match routine stays in the executable .text
cave. Existing resource entries are untouched: this only adds unused space
after them.

The region opens with MAGIC so a re-run can recognise its own work and stay
idempotent rather than growing the file every time.

    python tools/pe_space.py plan  <exe>
    python tools/pe_space.py apply <exe>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup_paths

IMAGE_BASE = 0x400000
MAGIC = b"K1MAPNTS"
HEADER_BYTES = 16          # MAGIC + 8 reserved, then the table
REGION_BYTES = 0x2000      # 8 KB: 8176 B usable = 511 entries of headroom


def _pe(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    return pe, nsec, optsz, opt, opt + optsz


def sections(data):
    _pe_off, nsec, _optsz, _opt, sec = _pe(data)
    out = []
    for i in range(nsec):
        o = sec + i * 40
        vsize, rva, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append({"name": data[o:o + 8].rstrip(b"\0").decode("latin-1"),
                    "hdr": o, "vsize": vsize, "rva": rva,
                    "rawsize": rawsize, "rawptr": rawptr})
    return out


def rva_to_off(data, rva):
    """File offset for a virtual address. NOT `va - IMAGE_BASE`: that identity
    only holds for .text, whose raw pointer happens to equal its RVA."""
    for s in sections(data):
        if s["rva"] <= rva < s["rva"] + max(s["vsize"], s["rawsize"]):
            return s["rawptr"] + (rva - s["rva"])
    raise ValueError("RVA 0x%X is not inside any section" % rva)


def find_region(data):
    """(region_rva, usable_bytes) if we already reserved space, else None."""
    last = sections(data)[-1]
    end_rva = last["rva"] + last["rawsize"]
    for cand in range(last["rva"], end_rva, 0x1000):
        try:
            off = rva_to_off(data, cand)
        except ValueError:
            continue
        if data[off:off + len(MAGIC)] == MAGIC:
            return cand, end_rva - cand - HEADER_BYTES
    return None


def plan(exe_path, quiet=False):
    data = bytearray(open(exe_path, "rb").read())
    pe, nsec, _optsz, opt, _sec = _pe(data)
    secs = sections(data)
    last = secs[-1]
    align = struct.unpack_from("<I", data, opt + 32)[0]
    size_of_image = struct.unpack_from("<I", data, opt + 56)[0]

    existing = find_region(data)
    if not quiet:
        print("file:            %s (%d bytes)" % (exe_path, len(data)))
        print("sections:        %d, last is %s" % (nsec, last["name"]))
        print("  %s rva 0x%X vsize 0x%X rawsize 0x%X rawptr 0x%X"
              % (last["name"], last["rva"], last["vsize"], last["rawsize"],
                 last["rawptr"]))
        print("SizeOfImage:     0x%X   SectionAlignment: 0x%X"
              % (size_of_image, align))
    if existing:
        rva, usable = existing
        if not quiet:
            print("\nalready reserved: region at VA 0x%X, %d usable bytes "
                  "(%d entries at 16 B) - nothing to do"
                  % (IMAGE_BASE + rva + HEADER_BYTES, usable, usable // 16))
        return data, rva, False

    if last["rawptr"] + last["rawsize"] != len(data):
        raise SystemExit("last section's raw data does not end at EOF (0x%X vs "
                         "0x%X) - refusing to append"
                         % (last["rawptr"] + last["rawsize"], len(data)))
    region_rva = last["rva"] + last["rawsize"]
    if not quiet:
        print("\nwould reserve:   VA 0x%X .. 0x%X (%d bytes)"
              % (IMAGE_BASE + region_rva,
                 IMAGE_BASE + region_rva + REGION_BYTES, REGION_BYTES))
        print("  table area:    VA 0x%X, %d usable bytes (%d entries at 16 B)"
              % (IMAGE_BASE + region_rva + HEADER_BYTES,
                 REGION_BYTES - HEADER_BYTES, (REGION_BYTES - HEADER_BYTES) // 16))
        print("  %s vsize  0x%X -> 0x%X" % (last["name"], last["vsize"],
                                            region_rva - last["rva"] + REGION_BYTES))
        print("  %s rawsize 0x%X -> 0x%X" % (last["name"], last["rawsize"],
                                             last["rawsize"] + REGION_BYTES))
        print("  SizeOfImage  0x%X -> 0x%X" % (size_of_image,
                                               size_of_image + REGION_BYTES))
        print("  file grows   %d -> %d bytes" % (len(data), len(data) + REGION_BYTES))
        print("\n  the 'Hellspawn Reborn' watermark at file offset 0xAC0 is NOT "
              "touched (that is the point of extending a section instead of "
              "adding one)")
    return data, region_rva, True


def extend(data):
    """Reserve REGION_BYTES at the end of the last section, in memory.

    The byte-level half of `apply()`, split out so a pipeline that keeps the
    whole exe in one bytearray (the player-facing patcher) writes the same
    bytes as the dev tool instead of reimplementing the header edits.

    Returns (region_rva, changed); idempotent - `changed` is False and nothing
    is written if the region is already there.
    """
    existing = find_region(data)
    if existing:
        return existing[0], False

    last = sections(data)[-1]
    _pe_off, _nsec, _optsz, opt, _sec = _pe(data)
    if last["rawptr"] + last["rawsize"] != len(data):
        raise ValueError("last section's raw data does not end at EOF (0x%X vs "
                         "0x%X) - refusing to append"
                         % (last["rawptr"] + last["rawsize"], len(data)))
    region_rva = last["rva"] + last["rawsize"]
    size_of_image = struct.unpack_from("<I", data, opt + 56)[0]

    struct.pack_into("<I", data, last["hdr"] + 8,
                     region_rva - last["rva"] + REGION_BYTES)
    struct.pack_into("<I", data, last["hdr"] + 16, last["rawsize"] + REGION_BYTES)
    struct.pack_into("<I", data, opt + 56, size_of_image + REGION_BYTES)
    data += bytes(REGION_BYTES)
    off = rva_to_off(data, region_rva)
    data[off:off + len(MAGIC)] = MAGIC
    return region_rva, True


def apply(exe_path):
    data, region_rva, needed = plan(exe_path)
    if not needed:
        return 0
    secs = sections(data)
    last = secs[-1]
    pe, _nsec, _optsz, opt, _sec = _pe(data)
    watermark = bytes(data[0xAC0:0xAD0])

    backup = backup_paths.make_backup(exe_path, ".pre-pe-extend-backup")
    print("\nbacked up to %s" % backup)

    new_vsize = region_rva - last["rva"] + REGION_BYTES
    new_rawsize = last["rawsize"] + REGION_BYTES
    size_of_image = struct.unpack_from("<I", data, opt + 56)[0]

    extend(data)

    with open(exe_path, "wb") as fh:
        fh.write(data)

    # verify from disk, not from what we think we wrote
    written = bytearray(open(exe_path, "rb").read())
    w_last = sections(written)[-1]
    ok = True
    checks = [
        ("section count unchanged", len(sections(written)) == len(secs)),
        ("%s vsize" % last["name"], w_last["vsize"] == new_vsize),
        ("%s rawsize" % last["name"], w_last["rawsize"] == new_rawsize),
        ("SizeOfImage", struct.unpack_from("<I", written, opt + 56)[0]
         == size_of_image + REGION_BYTES),
        ("raw data still ends at EOF",
         w_last["rawptr"] + w_last["rawsize"] == len(written)),
        ("region reachable and marked", find_region(written) is not None),
        ("watermark at 0xAC0 preserved", bytes(written[0xAC0:0xAD0]) == watermark),
    ]
    for label, good in checks:
        print("   [%s] %s" % ("x" if good else " ", label))
        ok = ok and good
    if not ok:
        print("\nVERIFY FAILED - restore from %s" % backup)
        return 1
    rva, usable = find_region(written)
    print("\nreserved VA 0x%X, %d usable bytes (%d entries at 16 B)"
          % (IMAGE_BASE + rva + HEADER_BYTES, usable, usable // 16))
    print("revert with:  copy \"%s\" \"%s\"" % (backup, exe_path))
    return 0


def table_va(data):
    """VA the note table should be written at, or None if not reserved yet."""
    found = find_region(data)
    if not found:
        return None
    return IMAGE_BASE + found[0] + HEADER_BYTES


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("plan", "apply"):
        print(__doc__)
        raise SystemExit(2)
    if sys.argv[1] == "plan":
        plan(sys.argv[2])
        raise SystemExit(0)
    raise SystemExit(apply(sys.argv[2]))
