"""Dump the current Blender theme to XML in Blender's own preset format.

Blender's bundled Blender_Dark.xml is an empty stub -- the real dark theme lives
in C defaults -- so this reconstructs the authoritative dark reference by walking
the theme RNA. Colours are plain sRGB bytes (verified: XML #999999 == RNA 0.6),
so the conversion is just round(v * 255).

Usage:  blender -b --factory-startup --python dump_theme.py -- <out.xml>
"""
import sys
import bpy

out_path = sys.argv[sys.argv.index("--") + 1]
theme = bpy.context.preferences.themes[0]

SKIP_PROPS = {"rna_type"}
# RNA structs that are part of a theme; anything else is not serialised
def is_theme_struct(obj):
    return hasattr(obj, "bl_rna") and obj.bl_rna.identifier.startswith("Theme")


def fmt_float(v):
    s = "%.5f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def colour(vals):
    b = [max(0, min(255, int(round(v * 255)))) for v in vals]
    while len(b) < 4:
        b.append(255)
    if b[3] == 255:
        return "#%02x%02x%02x" % (b[0], b[1], b[2])
    return "#%02x%02x%02x%02x" % tuple(b)


def scalar(prop, v):
    if prop.type == "BOOLEAN":
        return "TRUE" if v else "FALSE"
    if prop.type == "ENUM":
        return v
    if prop.type == "FLOAT":
        if prop.array_length in (3, 4):
            return colour(v)
        if prop.array_length:
            return " ".join(fmt_float(x) for x in v)
        return fmt_float(v)
    if prop.type == "INT":
        return str(v)
    if prop.type == "STRING":
        return v
    return None


def props_of(obj):
    """Ordered (name, value) pairs for a struct, mirroring Blender's XML layout.

    Values are strings for scalars and structs/collections otherwise. RNA props
    that cannot be read (Theme.filepath and friends) are skipped.
    """
    items = []
    for prop in obj.bl_rna.properties:
        ident = prop.identifier
        if ident in SKIP_PROPS or prop.is_runtime:
            continue
        try:
            value = getattr(obj, ident)
        except (AttributeError, TypeError, RuntimeError):
            continue
        if prop.type == "POINTER":
            if hasattr(value, "bl_rna") and is_theme_struct(value):
                items.append((ident, value))
        elif prop.type == "COLLECTION":
            vals = list(value)
            if vals:
                items.append((ident, vals))
        else:
            text = scalar(prop, value)
            if text is not None:
                items.append((ident, text))
    return items


def emit(obj, tag, indent, out):
    pad = "  " * indent
    attrs = [(n, v) for n, v in props_of(obj) if isinstance(v, str)]
    kids = [(n, v) for n, v in props_of(obj) if not isinstance(v, str)]
    out.append(f"{pad}<{tag}")
    for name, value in attrs:
        out.append(f'{pad}  {name}="{value}"')
    out.append(f"{pad}  >")
    for name, value in kids:
        if isinstance(value, list):
            out.append(f"{pad}  <{name}>")
            for item in value:
                emit(item, item.bl_rna.identifier, indent + 2, out)
            out.append(f"{pad}  </{name}>")
        else:
            out.append(f"{pad}  <{name}>")
            emit(value, value.bl_rna.identifier, indent + 2, out)
            out.append(f"{pad}  </{name}>")
    out.append(f"{pad}</{tag}>")


lines = ["<bpy>"]
emit(theme, "Theme", 1, lines)

# <ThemeStyle> is not a child of Theme in RNA -- it is the UI font style
# (preferences.ui_styles), whose panel_title/widget/tooltip are ThemeFontStyle.
# Blender's own preset writes it as a sibling of <Theme> under <bpy>.
ui = bpy.context.preferences.ui_styles[0]
lines.append("  <ThemeStyle")
lines.append("    >")
for wrapper in ("panel_title", "widget", "tooltip"):
    lines.append(f"    <{wrapper}>")
    emit(getattr(ui, wrapper), "ThemeFontStyle", 3, lines)
    lines.append(f"    </{wrapper}>")
lines.append("  </ThemeStyle>")
lines.append("</bpy>")
lines.append("")

with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines))
print("WROTE", out_path, len(lines), "lines")
