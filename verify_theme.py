"""Load every generated theme in Blender and read every colour back.

This is the acceptance test for blender_themes.py: each theme is installed, then
every colour attribute written into the XML is read back through RNA and compared
with what was written. Attributes a given Blender version does not know are
reported as skipped -- that is expected, because the files carry the union of the
names across versions so one file serves 4.x and 5.x alike.

Usage:  blender -b --factory-startup --python verify_theme.py -- <dist-dir>
"""
import glob
import json
import os
import re
import sys

import bpy

dist = sys.argv[sys.argv.index("--") + 1]
SEGMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")


def norm(h):
    h = h.lower()
    return h[:-2] if len(h) == 9 and h.endswith("ff") else h


def to_hex(v):
    if not hasattr(v, "__len__"):
        return "#%02x%02x%02x" % tuple([int(round(v * 255))] * 3)
    b = [max(0, min(255, int(round(x * 255)))) for x in v]
    while len(b) < 4:
        b.append(255)
    if b[3] == 255:
        return "#%02x%02x%02x" % (b[0], b[1], b[2])
    return "#%02x%02x%02x%02x" % tuple(b)


def resolve(theme, rna_path, attr):
    """Return ('ok', value) | ('absent', None) | ('error', message)."""
    obj = theme
    for name, idx in SEGMENT.findall(rna_path):
        if not hasattr(obj, name):
            return "absent", None
        obj = getattr(obj, name)
        if idx != "":
            try:
                obj = obj[int(idx)]
            except (IndexError, TypeError):
                return "absent", None
    if not hasattr(obj, attr):
        return "absent", None
    try:
        return "ok", getattr(obj, attr)
    except Exception as e:                                  # noqa: BLE001
        return "error", str(e)


print("BLENDER", bpy.app.version_string)
total_ok = total_bad = total_skip = 0
for xml in sorted(glob.glob(os.path.join(dist, "*.xml"))):
    name = os.path.basename(xml)
    bpy.ops.preferences.theme_install(filepath=xml)
    probes = json.load(open(xml + ".probe.json", encoding="utf-8"))

    # theme_install edits the active theme; find the one that took the values
    theme = None
    want = probes[0][2] if probes else None
    for cand in bpy.context.preferences.themes:
        kind, value = resolve(cand, probes[0][0], probes[0][1])
        if kind == "ok" and norm(to_hex(value)) == norm(want):
            theme = cand
            break
    if theme is None:
        print(f"{name}: FAILED -- no theme matched after install")
        total_bad += len(probes)
        continue

    ok = bad = skip = 0
    for rna_path, attr, expected in probes:
        kind, value = resolve(theme, rna_path, attr)
        if kind == "absent":
            skip += 1
            continue
        if kind == "error":
            print(f"   {name}: cannot read {rna_path}.{attr}: {value}")
            bad += 1
            continue
        got = to_hex(value)
        if norm(got) != norm(expected):
            print(f"   {name}: {rna_path}.{attr} = {got}, wrote {expected}")
            bad += 1
        else:
            ok += 1
    print(f"{name}: {ok} matched, {skip} unknown to this Blender, {bad} wrong")
    total_ok += ok
    total_skip += skip
    total_bad += bad

print(f"\nTOTAL  matched={total_ok}  unknown={total_skip}  wrong={total_bad}")
if total_bad:
    raise SystemExit(1)
print("every colour this Blender knows round-tripped exactly")
