# -*- coding: utf-8 -*-
"""Render a mock Blender window for each generated theme.

The colours are read back out of the generated XML rather than duplicated here,
so the preview always shows what the file actually contains.

Run:  python preview_blender.py
"""
import os
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

from anime_palettes import hx, load_font   # noqa: E402  (self-contained)

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
W, H = 1200, 740
TOP_H = 30
STATUS_H = 24
RIGHT_W = 300
BOTTOM_H = 138


def load_theme(path):
    """rna_path -> {attr: value}.

    The RNA path is the chain of WRAPPER element names (<view_3d>, <space>,
    <wcol_regular>); the element inside a wrapper is its RNA *type*, not a path
    segment, so it must not appear in the key.
    """
    root = ET.parse(path).getroot()
    out = {}

    def record(elem, key):
        out.setdefault(key, {}).update(elem.attrib)
        for wrapper in elem:
            walk_wrapper(wrapper, key)

    def walk_wrapper(wrapper, prefix):
        base = f"{prefix}.{wrapper.tag}" if prefix else wrapper.tag
        groups = {}
        for c in wrapper:
            groups.setdefault(c.tag, []).append(c)
        for group in groups.values():
            if len(group) > 1:
                for i, elem in enumerate(group):
                    record(elem, f"{base}[{i}]")
            else:
                record(group[0], base)

    for child in root:
        if child.tag == "ThemeStyle":
            for wrapper in child:
                for elem in wrapper:
                    record(elem, f"style.{wrapper.tag}")
        else:
            for wrapper in child:
                walk_wrapper(wrapper, "")
    return out


def c(theme, path, attr, fallback="#888888"):
    v = theme.get(path, {}).get(attr, fallback)
    return hx(v if v.startswith("#") else "#" + v)


def render(name, theme):
    img = Image.new("RGB", (W, H), c(theme, "user_interface", "panel_back"))
    d = ImageDraw.Draw(img)
    f = load_font(0, 14)
    fsm = load_font(0, 12)
    fb = load_font(1, 14)

    top_fg = c(theme, "topbar.space", "text")
    d.rectangle([0, 0, W, TOP_H], fill=c(theme, "topbar.space", "header"))
    d.line([(0, TOP_H - 1), (W, TOP_H - 1)], fill=c(theme, "user_interface", "editor_border"))
    d.text((12, 8), "File", font=fsm, fill=top_fg)
    d.text((50, 8), "Edit", font=fsm, fill=top_fg)
    d.text((86, 8), "Render", font=fsm, fill=top_fg)
    d.text((142, 8), "Window", font=fsm, fill=top_fg)
    d.text((200, 8), "Help", font=fsm, fill=top_fg)
    d.text((W - 190, 8), "Layout   Modeling   Sculpting", font=fsm,
           fill=c(theme, "topbar.space", "text_hi"))

    # ---------------- 3D viewport ----------------
    vx0, vy0 = 0, TOP_H
    vx1, vy1 = W - RIGHT_W, H - BOTTOM_H - STATUS_H
    vh = 24
    d.rectangle([vx0, vy0, vx1, vy1], fill=c(theme, "view_3d.space.gradients", "gradient"))
    d.rectangle([vx0, vy0, vx1, vy0 + vh], fill=c(theme, "view_3d.space", "header"))
    d.line([(vx0, vy0 + vh - 1), (vx1, vy0 + vh - 1)],
           fill=c(theme, "user_interface", "editor_border"))
    d.text((10, vy0 + 6), "User Perspective", font=fsm,
           fill=c(theme, "view_3d.space", "header_text"))
    d.text((130, vy0 + 6), "(1) Collection", font=fsm,
           fill=c(theme, "view_3d.space", "header_text_hi"))
    d.text((vx1 - 240, vy0 + 6), "Object Mode   View   Select", font=fsm,
           fill=c(theme, "view_3d.space", "text"))

    cx, cy = (vx0 + vx1) // 2 - 40, (vy0 + vh + vy1) // 2
    grid = c(theme, "view_3d", "grid")
    gridmaj = c(theme, "view_3d", "grid_major")
    step = 34
    for i in range(-14, 15):
        col = gridmaj if i % 4 == 0 else grid
        d.line([(cx + i * step, vy0 + vh), (cx + i * step, vy1)], fill=col)
        d.line([(vx0, cy + i * step), (vx1, cy + i * step)], fill=col)

    # gizmo axes
    ax = {"x": c(theme, "user_interface", "axis_x"),
          "y": c(theme, "user_interface", "axis_y"),
          "z": c(theme, "user_interface", "axis_z")}
    ox, oy = vx1 - 90, vy1 - 70
    d.line([(ox, oy), (ox + 46, oy)], fill=ax["x"], width=2)
    d.line([(ox, oy), (ox, oy - 46)], fill=ax["z"], width=2)
    d.line([(ox, oy), (ox - 32, oy + 32)], fill=ax["y"], width=2)

    # a wireframe cube, some edges selected
    wire = c(theme, "view_3d", "wire")
    sel = c(theme, "view_3d", "edge_select")
    vs = c(theme, "view_3d", "vertex")
    vsel = c(theme, "view_3d", "vertex_select")
    s = 74
    pts = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]
    off = (40, -34)
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        d.line([a, b], fill=sel if i in (1, 2) else wire, width=2)
        d.line([(a[0] + off[0], a[1] + off[1]), (b[0] + off[0], b[1] + off[1])],
               fill=wire, width=2)
        d.line([a, (a[0] + off[0], a[1] + off[1])], fill=wire, width=2)
    for i, p in enumerate(pts):
        col = vsel if i in (1, 3) else vs
        d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=col)
    d.text((cx - s - 6, cy - s - 26), "Cube", font=fsm,
           fill=c(theme, "view_3d", "object_active"))

    # ---------------- right column ----------------
    rx = W - RIGHT_W
    # outliner
    oy0 = TOP_H
    oh = 210
    d.rectangle([rx, oy0, W, oy0 + oh], fill=c(theme, "outliner.space", "back"))
    d.rectangle([rx, oy0, W, oy0 + vh], fill=c(theme, "outliner.space", "header"))
    d.text((rx + 10, oy0 + 6), "Outliner", font=fsm,
           fill=c(theme, "outliner.space", "header_text"))
    rows = [("Scene Collection", None), ("Collection", None), ("Cube", "selected_object"),
            ("Camera", None), ("Light", None), ("Sphere", "active_object")]
    ry = oy0 + vh + 6
    for label, role in rows:
        if role == "selected_object":
            d.rectangle([rx, ry, W, ry + 22], fill=c(theme, "outliner", "selected_highlight"))
        col = c(theme, "outliner", "active_object") if role == "active_object" else \
              c(theme, "outliner.space", "text")
        d.text((rx + 16, ry + 4), label, font=fsm, fill=col)
        ry += 22
    d.line([(rx, oy0 + oh), (W, oy0 + oh)], fill=c(theme, "user_interface", "editor_border"))

    # properties widgets
    py0 = oy0 + oh
    ph = H - BOTTOM_H - STATUS_H - py0 - 96
    d.rectangle([rx, py0, W, py0 + ph], fill=c(theme, "properties.space", "back"))
    d.rectangle([rx, py0, W, py0 + vh], fill=c(theme, "properties.space", "header"))
    d.text((rx + 10, py0 + 6), "Properties", font=fsm,
           fill=c(theme, "properties.space", "header_text"))
    inner = c(theme, "user_interface.wcol_regular", "inner")
    inner_sel = c(theme, "user_interface.wcol_regular", "inner_sel")
    item = c(theme, "user_interface.wcol_regular", "item")
    wtxt = c(theme, "user_interface.wcol_regular", "text")
    wsel = c(theme, "user_interface.wcol_regular", "text_sel")
    wout = c(theme, "user_interface.wcol_regular", "outline")
    wy = py0 + vh + 10
    # a checkbox row (on and off)
    for label, on in (("Shadow", True), ("Wireframe", False)):
        d.rectangle([rx + 12, wy, rx + 26, wy + 14],
                    fill=inner_sel if on else inner, outline=wout)
        if on:
            d.line([(rx + 15, wy + 7), (rx + 18, wy + 11)], fill=wsel, width=2)
            d.line([(rx + 18, wy + 11), (rx + 23, wy + 3)], fill=wsel, width=2)
        d.text((rx + 34, wy - 2), label, font=fsm, fill=wtxt)
        wy += 24
    # slider
    d.text((rx + 12, wy - 2), "Scale", font=fsm, fill=wtxt)
    d.rectangle([rx + 90, wy, W - 16, wy + 15], fill=item, outline=wout)
    d.rectangle([rx + 90, wy, rx + 150, wy + 15], fill=inner_sel)
    d.text((rx + 96, wy - 2), "1.25", font=fsm, fill=wsel)
    wy += 28
    # radio buttons
    d.text((rx + 12, wy - 2), "Type", font=fsm, fill=wtxt)
    for i, lab in enumerate(("X", "Y", "Z")):
        bx = rx + 62 + i * 34
        d.ellipse([bx, wy, bx + 14, wy + 14], fill=inner_sel if i == 0 else inner,
                  outline=wout)
        d.text((bx + 4, wy - 2), lab, font=fsm, fill=wsel if i == 0 else wtxt)
    wy += 26
    # state colours
    d.text((rx + 12, wy - 2), "State", font=fsm, fill=wtxt)
    for i, key in enumerate(("error", "warning", "info", "success", "inner_key",
                             "inner_driven", "inner_overridden", "inner_changed")):
        bx = rx + 62 + (i % 4) * 56
        by = wy + (i // 4) * 20
        d.rectangle([bx, by, bx + 44, by + 14],
                    fill=c(theme, "user_interface.wcol_state", key))

    # ---------------- bottom: dope sheet ----------------
    by0 = H - BOTTOM_H - STATUS_H
    d.rectangle([0, by0, W, by0 + BOTTOM_H], fill=c(theme, "dopesheet_editor.space", "back"))
    d.rectangle([0, by0, W, by0 + vh], fill=c(theme, "dopesheet_editor.space", "header"))
    d.text((10, by0 + 6), "Dope Sheet", font=fsm,
           fill=c(theme, "dopesheet_editor.space", "header_text"))
    # channels
    ch_y = by0 + vh + 10
    for label in ("Cube", "Location", "Scale", "Camera"):
        d.text((14, ch_y + 2), label, font=fsm,
               fill=c(theme, "common.anim", "channel"))
        d.line([(120, ch_y + 9), (W - 10, ch_y + 9)],
               fill=c(theme, "dopesheet_editor", "grid"))
        ch_y += 22
    # keyframes
    keys = [(150, "keyframe"), (230, "keyframe"), (310, "keyframe_selected"),
            (390, "keyframe_extreme"), (470, "keyframe_breakdown"),
            (550, "keyframe_jitter"), (630, "keyframe_moving_hold"),
            (710, "keyframe"), (790, "keyframe_generated")]
    for i, label in enumerate(("Cube", "Location", "Scale", "Camera")):
        yy = by0 + vh + 14 + i * 22
        for kx, role in keys:
            col = c(theme, "common.anim", role)
            x = kx + i * 26
            d.rectangle([x, yy, x + 11, yy + 11], fill=col)
    # playhead
    px = 430
    d.line([(px, by0 + vh), (px, by0 + BOTTOM_H)], fill=c(theme, "common.anim", "playhead"), width=2)

    # ---------------- status bar ----------------
    sy = H - STATUS_H
    d.rectangle([0, sy, W, H], fill=c(theme, "statusbar.space", "header"))
    d.line([(0, sy), (W, sy)], fill=c(theme, "user_interface", "editor_border"))
    d.text((12, sy + 5), "Cube  |  Verts 8  |  Edges 12  |  Faces 6  |  Objects 4/4",
           font=fsm, fill=c(theme, "statusbar.space", "text"))
    d.text((W - 330, sy + 5), "Blender 5.2   |   Frame 24   |   Memory 82.4 MB",
           font=fsm, fill=c(theme, "statusbar.space", "text"))

    # ---------------- syntax strip ----------------
    ty = py0 + ph
    d.rectangle([rx, ty, W, ty + 96], fill=c(theme, "text_editor.space", "back"))
    d.rectangle([rx, ty, W, ty + vh], fill=c(theme, "text_editor.space", "header"))
    d.text((rx + 10, ty + 6), "Text Editor", font=fsm,
           fill=c(theme, "text_editor.space", "header_text"))
    lines = [
        [("# freeze the ocean", "syntax_comment")],
        [("def ", "syntax_keyword"), ("freeze", "syntax_builtin"),
         ("(level=", "syntax_symbols"), ("3", "syntax_numbers"),
         ("):", "syntax_symbols")],
        [("    name = ", "syntax_symbols"), ('"Miku"', "syntax_string")],
        [("    return ", "syntax_keyword"), ("name", "syntax_reserved"),
         (" @ ", "syntax_special"), ("level", "syntax_preprocessor")],
    ]
    ly = ty + vh + 5
    for i, toks in enumerate(lines):
        d.text((rx + 12, ly), str(i + 1), font=fsm,
               fill=c(theme, "text_editor", "line_numbers"))
        x = rx + 34
        for text, role in toks:
            font = fb if role == "syntax_keyword" else fsm
            d.text((x, ly), text, font=font, fill=c(theme, "text_editor", role))
            x += font.getlength(text)
        ly += 15

    # title
    d.rectangle([0, TOP_H, 300, TOP_H + 20], fill=c(theme, "user_interface", "panel_header"))
    d.text((8, TOP_H + 4), name, font=fb,
           fill=c(theme, "user_interface", "panel_text"))
    return img


def main():
    names = sorted(f for f in os.listdir(DIST) if f.endswith(".xml"))
    imgs = []
    for fn in names:
        theme = load_theme(os.path.join(DIST, fn))
        img = render(fn[:-4], theme)
        out = os.path.join(DIST, "preview_" + fn[:-4] + ".png")
        img.save(out)
        imgs.append(img)
        print(f"wrote {os.path.basename(out)}")
    Wc = max(i.width for i in imgs) + 40
    Hc = sum(i.height for i in imgs) + 40 * (len(imgs) + 1)
    canvas = Image.new("RGB", (Wc, Hc), "#1b1b1b")
    y = 40
    for i in imgs:
        canvas.paste(i, (20, y))
        y += i.height + 40
    canvas.save(os.path.join(DIST, "preview_all.png"))
    print(f"wrote preview_all.png  {canvas.size[0]}x{canvas.size[1]}")


if __name__ == "__main__":
    main()
