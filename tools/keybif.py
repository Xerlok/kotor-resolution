"""
Reader for BioWare Aurora Engine KEY/BIF archives (chitin.key + data/*.bif).

Spec: BioWare Aurora Engine Key and BIF File Formats (bioware.com, via nwn.wiki).
All integers are little-endian. WORD = 2 bytes, DWORD = 4 bytes.

How the pieces fit together:
- The .key file is an index: for every resource (by ResRef + ResourceType) it
  stores a ResID that encodes *which* .bif file holds it, and *where* in that
  .bif's own resource table to look.
- Each .bif file has its own resource table with byte offsets into itself.

So to extract a resource you: look it up in the KEY to find (bif_index,
resource_index), open that BIF, and index into its resource table.
"""

import struct
from dataclasses import dataclass

RESTYPE_GUI = 2047  # from Table 1.3.1 in the Key/BIF spec


@dataclass
class BifFileEntry:
    filename: str
    file_size: int


@dataclass
class KeyEntry:
    resref: str
    res_type: int
    bif_index: int      # x: which BIF (index into the File Table)
    resource_index: int  # y: index into that BIF's Variable Resource Table


@dataclass
class KeyFile:
    bif_files: list  # list[BifFileEntry], index == bif_index
    entries: list    # list[KeyEntry]

    def find(self, resref, res_type):
        resref = resref.lower()
        for e in self.entries:
            if e.res_type == res_type and e.resref.lower() == resref:
                return e
        return None

    def list_by_type(self, res_type):
        return [e for e in self.entries if e.res_type == res_type]


def read_key(path):
    with open(path, "rb") as f:
        data = f.read()

    file_type, file_version = data[0:4], data[4:8]
    if file_type != b"KEY ":
        raise ValueError(f"not a KEY file (FileType={file_type!r})")

    (bif_count, key_count, offset_to_file_table, offset_to_key_table,
     _build_year, _build_day) = struct.unpack_from("<IIIIII", data, 8)
    # header is 8 + 6*4 = 32 bytes, then 32 reserved bytes -> 64 total (unused here)

    # --- File Table: one entry per BIF, gives us its filename ---
    bif_files = []
    off = offset_to_file_table
    for _ in range(bif_count):
        file_size, filename_offset, filename_size, _drives = struct.unpack_from(
            "<IIHH", data, off
        )
        name = data[filename_offset: filename_offset + filename_size].decode("ascii")
        bif_files.append(BifFileEntry(filename=name, file_size=file_size))
        off += 12  # DWORD + DWORD + WORD + WORD

    # --- Key Table: one entry per resource ---
    entries = []
    off = offset_to_key_table
    for _ in range(key_count):
        resref_raw = data[off: off + 16]
        res_type, res_id = struct.unpack_from("<HI", data, off + 16)
        resref = resref_raw.split(b"\x00", 1)[0].decode("ascii")
        bif_index = res_id >> 20
        resource_index = res_id & 0xFFFFF  # low 20 bits
        entries.append(KeyEntry(resref, res_type, bif_index, resource_index))
        off += 16 + 2 + 4  # ResRef + ResourceType(WORD) + ResID(DWORD)

    return KeyFile(bif_files=bif_files, entries=entries)


def extract_resource(bif_path, resource_index):
    """Pull the raw bytes for one resource out of a .bif file by its index
    into that BIF's own Variable Resource Table (the 'y' from a KeyEntry)."""
    with open(bif_path, "rb") as f:
        data = f.read()

    file_type = data[0:4]
    if file_type != b"BIFF":
        raise ValueError(f"not a BIF file (FileType={file_type!r})")

    variable_count, _fixed_count, table_offset = struct.unpack_from("<III", data, 8)
    if resource_index >= variable_count:
        raise IndexError(
            f"resource index {resource_index} out of range "
            f"(this BIF has {variable_count} variable resources)"
        )

    entry_off = table_offset + resource_index * 16  # ID, Offset, FileSize, ResType
    _id, offset, file_size, res_type = struct.unpack_from("<IIII", data, entry_off)
    return data[offset: offset + file_size], res_type
