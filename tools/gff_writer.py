"""
The write side of gff.py — takes a GFFStruct tree (same shape our reader
produces) and serializes it back into valid GFF V3.2 bytes.

Mirrors the reader section-by-section: Struct Array, Field Array, Label
Array, Field Data, Field Indices, List Indices — see gff.py's module
docstring for what each section is.

The one tricky bit: the spec requires the TOP-LEVEL struct to sit at index 0
in the Struct Array. Our traversal naturally wants to write children before
their parents (a field can't record "my child struct is at index N" until
the child has actually been written and given an index N). So we reserve
slot 0 for the top-level struct up front, and everything else gets appended
starting from index 1.
"""

import struct
from . import gff


def dumps(gff_file):
    structs_out = [None]  # slot 0 reserved for the top-level struct
    fields_out = []
    labels_list = []
    labels_index = {}
    field_data = bytearray()
    field_indices = []  # flat list of ints (struct indices)
    list_indices = bytearray()

    def get_label(text):
        if text not in labels_index:
            labels_index[text] = len(labels_list)
            labels_list.append(text)
        return labels_index[text]

    def add_field_data(b):
        offset = len(field_data)
        field_data.extend(b)
        return offset

    def write_list(struct_list):
        indices = [write_struct(s) for s in struct_list]
        offset = len(list_indices)
        list_indices.extend(struct.pack(f"<I{len(indices)}I", len(indices), *indices))
        return offset

    def write_field(f):
        t = f.type
        if t == gff.BYTE:
            raw = bytes([f.value & 0xFF]) + b"\x00" * 3
        elif t == gff.CHAR:
            raw = bytes([ord(f.value) & 0xFF]) + b"\x00" * 3
        elif t == gff.WORD:
            raw = struct.pack("<H", f.value) + b"\x00" * 2
        elif t == gff.SHORT:
            raw = struct.pack("<h", f.value) + b"\x00" * 2
        elif t == gff.DWORD:
            raw = struct.pack("<I", f.value)
        elif t == gff.INT:
            raw = struct.pack("<i", f.value)
        elif t == gff.FLOAT:
            raw = struct.pack("<f", f.value)
        elif t == gff.DWORD64:
            raw = struct.pack("<I", add_field_data(struct.pack("<Q", f.value)))
        elif t == gff.INT64:
            raw = struct.pack("<I", add_field_data(struct.pack("<q", f.value)))
        elif t == gff.DOUBLE:
            raw = struct.pack("<I", add_field_data(struct.pack("<d", f.value)))
        elif t == gff.CEXOSTRING:
            b_ = f.value.encode("latin-1")
            raw = struct.pack("<I", add_field_data(struct.pack("<I", len(b_)) + b_))
        elif t == gff.RESREF:
            b_ = f.value.encode("latin-1")[:16]
            raw = struct.pack("<I", add_field_data(bytes([len(b_)]) + b_))
        elif t == gff.CEXOLOCSTRING:
            v = f.value
            body = struct.pack("<ii", v["str_ref"], len(v["substrings"]))
            for sid, text in v["substrings"].items():
                bt = text.encode("latin-1")
                body += struct.pack("<ii", sid, len(bt)) + bt
            blob = struct.pack("<I", len(body)) + body
            raw = struct.pack("<I", add_field_data(blob))
        elif t == gff.VOID:
            raw = struct.pack("<I", add_field_data(struct.pack("<I", len(f.value)) + f.value))
        elif t == gff.ORIENTATION:
            raw = struct.pack("<I", add_field_data(struct.pack("<4f", *f.value)))
        elif t == gff.VECTOR:
            raw = struct.pack("<I", add_field_data(struct.pack("<3f", *f.value)))
        elif t == gff.STRREF:
            raw = struct.pack("<I", add_field_data(struct.pack("<Ii", 4, f.value)))
        elif t == gff.STRUCT:
            raw = struct.pack("<I", write_struct(f.value))
        elif t == gff.LIST:
            raw = struct.pack("<I", write_list(f.value))
        else:
            raise ValueError(f"cannot write GFF field type {t} (label={f.label!r})")

        field_index = len(fields_out)
        fields_out.append((t, get_label(f.label), raw))
        return field_index

    def write_struct(s, reserved_index=None):
        idx = reserved_index
        if idx is None:
            idx = len(structs_out)
            structs_out.append(None)

        field_idxs = [write_field(f) for f in s.fields.values()]
        count = len(field_idxs)
        if count == 0:
            data_or_offset = 0
        elif count == 1:
            data_or_offset = field_idxs[0]
        else:
            data_or_offset = len(field_indices) * 4  # byte offset, not element index
            field_indices.extend(field_idxs)

        structs_out[idx] = (s.struct_id, data_or_offset, count)
        return idx

    write_struct(gff_file.top, reserved_index=0)

    struct_bytes = b"".join(struct.pack("<III", t, d, c) for t, d, c in structs_out)
    field_bytes = b"".join(struct.pack("<II", t, li) + raw for t, li, raw in fields_out)
    label_bytes = b"".join(lbl.encode("ascii").ljust(16, b"\x00")[:16] for lbl in labels_list)
    field_indices_bytes = struct.pack(f"<{len(field_indices)}I", *field_indices)

    header_size = 56
    struct_off = header_size
    field_off = struct_off + len(struct_bytes)
    label_off = field_off + len(field_bytes)
    fielddata_off = label_off + len(label_bytes)
    fieldidx_off = fielddata_off + len(field_data)
    listidx_off = fieldidx_off + len(field_indices_bytes)

    header = struct.pack(
        "<4s4sIIIIIIIIIIII",
        gff_file.file_type.encode("ascii"),
        gff_file.file_version.encode("ascii"),
        struct_off, len(structs_out),
        field_off, len(fields_out),
        label_off, len(labels_list),
        fielddata_off, len(field_data),
        fieldidx_off, len(field_indices_bytes),
        listidx_off, len(list_indices),
    )

    return (
        header + struct_bytes + field_bytes + label_bytes
        + bytes(field_data) + field_indices_bytes + bytes(list_indices)
    )
