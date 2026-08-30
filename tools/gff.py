"""
Reader for BioWare's Generic File Format (GFF) — V3.2.

Spec: BioWare Aurora Engine Generic File Format (bioware.com, via nwn.wiki).
KOTOR's .gui files (UI layouts) are GFF underneath, same as .utc, .are, etc.

Layout (all offsets are byte offsets from the start of the file):
  Header | Struct Array | Field Array | Label Array | Field Data | Field Indices | List Indices

The header is 56 bytes: FileType(4) + FileVersion(4) + 12 DWORDs of
(offset, count) pairs for the six sections below the header.

A Field's value is either stored inline in its own 4-byte slot ("simple"
types: BYTE/CHAR/WORD/SHORT/DWORD/INT/FLOAT) or as a byte offset into the
Field Data block ("complex" types). Struct and List are special-cased even
further — see FIELD_TYPES and _read_field below.
"""

import struct
from dataclasses import dataclass, field as dc_field

# Field.Type values (Table 3.4b in the base Aurora spec)
BYTE, CHAR, WORD, SHORT, DWORD, INT, DWORD64, INT64, FLOAT, DOUBLE, \
    CEXOSTRING, RESREF, CEXOLOCSTRING, VOID, STRUCT, LIST = range(16)

# KotOR's Odyssey engine extends the base Aurora type list with three more,
# used by .gui/.git/.utc etc. Not in BioWare's original Aurora GFF doc —
# confirmed against a community GFF implementation (KotOR-Bioware-Libs/GFF.pm).
ORIENTATION = 16  # 4 floats (quaternion), 16 bytes in Field Data
VECTOR = 17       # 3 floats (position or RGB color), 12 bytes in Field Data
STRREF = 18       # 8 bytes in Field Data: a leading DWORD (always 4) + the value DWORD

SIMPLE_TYPES = {BYTE, CHAR, WORD, SHORT, DWORD, INT, FLOAT}


@dataclass
class GFFField:
    label: str
    type: int
    value: object  # python value, or a GFFStruct, or a list[GFFStruct]


@dataclass
class GFFStruct:
    struct_id: int
    fields: dict = dc_field(default_factory=dict)  # label -> GFFField, insertion-ordered

    def __getitem__(self, label):
        return self.fields[label].value

    def __contains__(self, label):
        return label in self.fields


class GFFFile:
    def __init__(self, file_type, file_version, top_level):
        self.file_type = file_type
        self.file_version = file_version
        self.top = top_level


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    return loads(data)


def loads(data):
    file_type = data[0:4].decode("ascii")
    file_version = data[4:8].decode("ascii")
    if file_version != "V3.2":
        raise ValueError(f"unsupported GFF version {file_version!r} (expected 'V3.2')")

    (struct_off, struct_count, field_off, field_count, label_off, label_count,
     fielddata_off, fielddata_count, fieldidx_off, fieldidx_count,
     listidx_off, listidx_count) = struct.unpack_from("<IIIIIIIIIIII", data, 8)

    # --- Struct Array: (Type, DataOrDataOffset, FieldCount), 12 bytes each ---
    structs_raw = [
        struct.unpack_from("<III", data, struct_off + i * 12)
        for i in range(struct_count)
    ]

    # --- Field Array: (Type, LabelIndex, DataOrDataOffset-raw-bytes), 12 bytes each ---
    fields_raw = []
    for i in range(field_count):
        ftype, label_idx = struct.unpack_from("<II", data, field_off + i * 12)
        raw = data[field_off + i * 12 + 8: field_off + i * 12 + 12]
        fields_raw.append((ftype, label_idx, raw))

    # --- Label Array: 16-byte fixed strings, null-padded, not null-terminated ---
    labels = []
    for i in range(label_count):
        raw = data[label_off + i * 16: label_off + i * 16 + 16]
        labels.append(raw.split(b"\x00", 1)[0].decode("ascii"))

    field_data = data[fielddata_off: fielddata_off + fielddata_count]
    field_indices = data[fieldidx_off: fieldidx_off + fieldidx_count]
    list_indices = data[listidx_off: listidx_off + listidx_count]

    def read_cexostring(off):
        (size,) = struct.unpack_from("<I", field_data, off)
        text = field_data[off + 4: off + 4 + size].decode("latin-1")
        return text

    def read_resref(off):
        size = field_data[off]
        text = field_data[off + 1: off + 1 + size].decode("latin-1")
        return text

    def read_cexolocstring(off):
        total_size, str_ref, str_count = struct.unpack_from("<Iii", field_data, off)
        pos = off + 12
        substrings = {}
        for _ in range(str_count):
            string_id, str_len = struct.unpack_from("<ii", field_data, pos)
            pos += 8
            text = field_data[pos: pos + str_len].decode("latin-1")
            pos += str_len
            substrings[string_id] = text
        return {"str_ref": str_ref, "substrings": substrings}

    def read_void(off):
        (size,) = struct.unpack_from("<I", field_data, off)
        return field_data[off + 4: off + 4 + size]

    def read_list(off):
        (size,) = struct.unpack_from("<I", list_indices, off)
        indices = struct.unpack_from(f"<{size}I", list_indices, off + 4)
        return [read_struct(i) for i in indices]

    def read_field(index):
        ftype, label_idx, raw = fields_raw[index]
        label = labels[label_idx]

        if ftype == BYTE:
            value = raw[0]
        elif ftype == CHAR:
            value = chr(raw[0])
        elif ftype == WORD:
            value = struct.unpack("<H", raw[:2])[0]
        elif ftype == SHORT:
            value = struct.unpack("<h", raw[:2])[0]
        elif ftype == DWORD:
            value = struct.unpack("<I", raw)[0]
        elif ftype == INT:
            value = struct.unpack("<i", raw)[0]
        elif ftype == FLOAT:
            value = struct.unpack("<f", raw)[0]
        elif ftype in (DWORD64, INT64, DOUBLE):
            (off,) = struct.unpack("<I", raw)
            if ftype == DWORD64:
                value = struct.unpack_from("<Q", field_data, off)[0]
            elif ftype == INT64:
                value = struct.unpack_from("<q", field_data, off)[0]
            else:
                value = struct.unpack_from("<d", field_data, off)[0]
        elif ftype == CEXOSTRING:
            (off,) = struct.unpack("<I", raw)
            value = read_cexostring(off)
        elif ftype == RESREF:
            (off,) = struct.unpack("<I", raw)
            value = read_resref(off)
        elif ftype == CEXOLOCSTRING:
            (off,) = struct.unpack("<I", raw)
            value = read_cexolocstring(off)
        elif ftype == VOID:
            (off,) = struct.unpack("<I", raw)
            value = read_void(off)
        elif ftype == ORIENTATION:
            (off,) = struct.unpack("<I", raw)
            value = struct.unpack_from("<4f", field_data, off)
        elif ftype == VECTOR:
            (off,) = struct.unpack("<I", raw)
            value = struct.unpack_from("<3f", field_data, off)
        elif ftype == STRREF:
            (off,) = struct.unpack("<I", raw)
            _leading, value = struct.unpack_from("<Ii", field_data, off)
        elif ftype == STRUCT:
            (struct_index,) = struct.unpack("<I", raw)
            value = read_struct(struct_index)
        elif ftype == LIST:
            (off,) = struct.unpack("<I", raw)
            value = read_list(off)
        else:
            raise ValueError(f"unknown GFF field type {ftype} (label={label!r})")

        return GFFField(label=label, type=ftype, value=value)

    def read_struct(struct_index):
        struct_type, data_or_offset, field_count_ = structs_raw[struct_index]
        result = GFFStruct(struct_id=struct_type)

        if field_count_ == 0:
            field_idxs = []
        elif field_count_ == 1:
            field_idxs = [data_or_offset]
        else:
            field_idxs = struct.unpack_from(
                f"<{field_count_}I", field_indices, data_or_offset
            )

        for fi in field_idxs:
            gf = read_field(fi)
            result.fields[gf.label] = gf
        return result

    top_level = read_struct(0)
    return GFFFile(file_type=file_type, file_version=file_version, top_level=top_level)
