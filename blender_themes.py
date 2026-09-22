# -*- coding: utf-8 -*-
"""Generate Blender theme XML from the anime palettes.

Blender theme presets are XML files in
  <blender>/<version>/scripts/presets/interface_theme/
Their attribute names are RNA property names, and Blender **silently ignores**
ones it does not know -- the same trap as the IDEA .icls work. So nothing here is
guessed: the structure, the attribute names and every non-colour value come from
Blender's own files.

References (all required to exist):
  <ver>/scripts/presets/interface_theme/Blender_Light.xml   the official light preset
  blender/dark_<major>_<minor>.xml                          an RNA dump of the default
                                                            dark theme (dump_theme.py),
                                                            because the bundled dark
                                                            preset is an empty stub

The output carries the UNION of the attribute names across references, because
Blender renamed many of them between 4.x and 5.x (frame_current -> playhead,
sub_back -> panel_sub_back, edge_seam -> seam, ...). Each version ignores names it
does not know, so a single file works on 4.5, 5.0 and 5.2 at once.

Colour policy:
  * surfaces, text, selection and highlights come straight from the anime palette;
  * Blender's semantic colours (crease / seam / sharp / bevel / freestyle, node
    categories, collection and strip ramps, axis colours) keep their HUE -- those
    hues are a mental model modellers rely on -- and only take the theme's
    saturation/value bands;
  * numeric sizes, fonts and behaviour flags keep Blender's own values.

Run:  python blender_themes.py
      then verify with:  blender -b --factory-startup --python verify_theme.py
"""
import colorsys
import copy
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))

# The shared palette values live in anime_palettes (generated from the sibling IDEA
# project), so this repository is self-contained and imports nothing from outside it.
import anime_palettes as ap
from anime_palettes import adjust

OUT = os.path.join(HERE, "dist")
BLENDER_ROOTS = [r"E:\apps\Blender", r"C:\Program Files\Blender Foundation",
                 r"D:\Program Files\Blender Foundation", "/usr/share/blender",
                 "/Applications/Blender.app/Contents/Resources"]

THEME_NAMES = list(ap.PALETTES)
FILE_OF = {n: n.replace(" ", "_") + ".xml" for n in THEME_NAMES}

# RNA props present in the dump but not written by Blender's preset writer.
# Keeping them is deliberate: they are real theme properties, so a version that
# knows them gets a fully specified theme instead of a default.
EXTRA_ALLOWED = {"link", "panel_active", "channel_selected", "scene_strip_range",
                 "match", "keyframe_border", "keyframe_border_selected"}
DROP_ATTRS = {"filepath", "name", "theme_area"}

ARRAY_COUNTS = {"ThemeBoneColorSet": 20, "ThemeCollectionColor": 8,
                "ThemeStripColor": 9}


# --------------------------------------------------------------- references --
def find_references():
    """(light preset, dark dump) per Blender version; both must exist."""
    refs = []
    for root in BLENDER_ROOTS:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            base = os.path.join(root, entry)
            if not os.path.isdir(base):
                continue
            for ver in sorted(os.listdir(base)):
                light = os.path.join(base, ver, "scripts", "presets",
                                     "interface_theme", "Blender_Light.xml")
                if not os.path.isfile(light):
                    continue
                dump = os.path.join(HERE, "dark_" + ver.replace(".", "_") + ".xml")
                if os.path.isfile(dump):
                    refs.append({"version": ver, "light": light, "dark": dump})
    # newest first: it becomes the base, and older versions are merged in only to
    # ADD the attributes they have and newer ones dropped. Values must not be
    # taken from an older version -- Blender's defaults drift between releases
    # (e.g. wcol_list_item.outline is opaque in 4.5 and transparent in 5.2), so an
    # old value is a stale value.
    def key(ref):
        return tuple(int(x) for x in ref["version"].split(".") if x.isdigit())
    return sorted(refs, key=key, reverse=True)


def merge(dst, src):
    """Union src into dst: missing attributes added, extra children inserted.

    Elements are matched by tag in document order, which is safe here because
    repeated elements (spaces, wcol_* sets, colour arrays) appear in the same
    order in every reference.
    """
    for k in DROP_ATTRS:
        dst.attrib.pop(k, None)
        src.attrib.pop(k, None)
    for k, v in src.attrib.items():
        dst.attrib.setdefault(k, v)

    def by_tag(node):
        out = {}
        for c in node:
            out.setdefault(c.tag, []).append(c)
        return out

    dst_by, src_by = by_tag(dst), by_tag(src)
    for tag, src_list in src_by.items():
        dst_list = dst_by.setdefault(tag, [])
        for i, sc in enumerate(src_list):
            if i < len(dst_list):
                merge(dst_list[i], sc)
            else:
                clone = copy.deepcopy(sc)
                pos = list(dst).index(dst_list[-1]) + 1 if dst_list else len(list(dst))
                dst.insert(pos, clone)
                dst_list.append(clone)
    return dst


def skeleton(variant):
    refs = find_references()
    if not refs:
        sys.exit("no Blender install with both a light preset and a dark dump "
                 "found; looked in %s" % BLENDER_ROOTS)
    base, used = None, []
    for ref in refs:
        root = ET.parse(ref["light" if variant == "light" else "dark"]).getroot()
        if base is None:
            base = root
        else:
            merge(base, root)
        used.append(ref["version"])
    for child in list(base):
        child.attrib.pop("name", None)
    return base, used


# ------------------------------------------------------ colour helpers / bands --
def hexv(v):
    if not isinstance(v, str) or not v.startswith("#"):
        return None
    body = v[1:]
    return body if len(body) in (6, 8) else None


def alpha_of(v):
    body = hexv(v)
    return body[6:8].lower() if body and len(body) == 8 else ""


def with_alpha(rgb, a):
    return rgb + a if a else rgb


def hsv_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def tone(ref_value, dark):
    """Keep the reference hue, restate it in the theme's saturation/value bands."""
    body = hexv(ref_value)
    r, g, b = (int(body[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if dark:
        s, v = min(max(s, 0.35), 0.80), min(max(v, 0.55), 0.92)
    else:
        s, v = min(max(s, 0.45), 0.90), min(max(v, 0.35), 0.70)
    return with_alpha(hsv_hex(h, s, v), alpha_of(ref_value))


def brighten(hexstr, factor):
    body = hexv(hexstr)
    r, g, b = (int(body[i:i + 2], 16) for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return hsv_hex(h, s, min(1.0, v * factor))


def contrast(c1, c2):
    def lum(h):
        h = h.lstrip("#")[:6]
        c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = lum(c1), lum(c2)
    return round((max(a, b) + 0.05) / (min(a, b) + 0.05), 2)


# ------------------------------------------------------------------ palettes --
def palette(name):
    """Anime palette p: the IDEA UI palette plus the roles a 3D app needs."""
    p = dict(ap.PALETTES[name])       # already carries the IDEA-side readability pass
    dark = p["dark"]
    # The editor background is the colour scheme's own background. Brightening it
    # would break the syntax palette: those colours were verified against exactly
    # this value in the IDEA schemes, and re-toning the background invalidates
    # that measured contrast. Wire and vertex colours are set to stay legible on it.
    p["space_back"] = p["win"]
    p["wire"] = p["fg3"] if dark else p["fg2"]
    p["wire_edit"] = p["fg2"] if dark else p["fg"]
    p["vertex"] = p["fg2"]
    p["text"] = p["fg2"]
    p["text_hi"] = p["accent"]
    p["on_accent"] = p["onAccent"]
    p["axis_x"] = tone("#e5484d", dark)
    p["axis_y"] = tone("#62b543", dark)
    p["axis_z"] = tone("#3d8bfd", dark)
    p["axis_w"] = tone("#a066d9", dark)
    p["rgb_a"] = tone("#3f9e4d", dark)
    p["rgb_b"] = tone("#c0392b", dark)
    # veils stay black: Blender uses them as a shade multiplier, and the usual
    # tone pass would lift them to grey
    p["veil"] = "#000000"
    r = ap.EDITOR_ROLES[name]
    p.update({
        "syn_keyword": r["keyword"], "syn_string": r["string"],
        "syn_number": r["number"], "syn_comment": r["comment"],
        "syn_builtin": r["predefined"], "syn_special": r["escape"],
        "syn_symbols": r["operator"], "syn_preprocessor": r["doc_tag"],
        "line_numbers": r["comment"],
    })
    return p


# Reference-valued fallback for anything the tables below do not name: keep the
# hue (so semantics survive) and restate the tone. Every fallback hit is reported
# so the tables can be completed instead of silently drifting.
DIRECT = {
    # panel / space surfaces and their text
    "back": "space_back", "header": "panel", "title": "fg", "text": "text",
    "text_hi": "text_hi", "header_text": "fg", "header_text_hi": "text_hi",
    "text_sel": "on_accent", "tab_back": "panel", "tab_active": "raised",
    "tab_inactive": "hover", "tab_outline": "border", "button": "raised",
    "button_title": "fg", "button_text": "text", "button_text_hi": "text_hi",
    "navigation_bar": "space_back", "execution_buts": "space_back",
    "panel_back": "panel", "panel_header": "panel", "panel_text": "fg",
    "panel_title": "fg", "panel_outline": "border", "panel_sub_back": "raised",
    "sub_back": "raised", "editor_border": "border", "editor_outline": "border",
    "editor_outline_active": "accent", "widget_emboss": "border",
    "widget_text_cursor": "accent", "transparent_checker_primary": "raised",
    "transparent_checker_secondary": "panel",
    # widgets
    "outline": "border", "outline_sel": "accent", "inner": "raised",
    "inner_sel": "accent", "item": "panel",
    # gradient viewport background
    "gradient": "space_back", "high_gradient": "space_back",
    # lists, menus, outliner
    "list": "panel", "list_title": "fg", "list_text": "text",
    "list_text_hi": "text_hi", "menu_back": "raised", "menu_item": "raised",
    "tooltip": "raised", "active": "accent", "active_object": "gold",
    "edited_object": "info", "selected_highlight": "sel",
    "selected_object": "accent", "row_alternate": "raised",
    # grids and borders
    "grid": "border", "grid_major": "fg3", "clipping_border_3d": "border",
    # 3D viewport
    "object_selected": "gold", "object_active": "accent", "camera": "fg3",
    "empty": "fg3", "speaker": "fg3", "light": "gold", "bundle_solid": "fg3",
    "bone_solid": "fg3", "bone_pose": "info", "bone_pose_active": "accent",
    "bone_locked_weight": "err", "wire": "wire", "wire_edit": "wire_edit",
    "wire_select": "accent", "vertex": "vertex", "vertex_select": "accent",
    "vertex_unreferenced": "fg3", "edge_select": "accent", "face": "vertex",
    "face_select": "accent", "face_back": "accent", "face_front": "accent",
    "face_mode_select": "accent", "edge_mode_select": "accent",
    "transform": "fg", "text_grease_pencil": "gold", "gp_vertex": "fg2",
    "gp_vertex_select": "accent", "gp_wire_edit": "wire_edit", "gp_wire": "wire",
    "vertex_normal": "info", "split_normal": "err", "skin_root": "warn",
    "nurb_uline": "fg3", "nurb_vline": "fg3", "nurb_sel_uline": "accent",
    "nurb_sel_vline": "accent", "extra_edge_len": "info",
    "extra_edge_angle": "info", "extra_face_angle": "info",
    "extra_face_area": "info",
    # node editor surfaces
    "node_backdrop": "raised", "node_outline": "border",
    "node_selected": "accent", "node_active": "accent", "noodle_curving": "fg3",
    # timeline and keyframes
    "playhead": "info", "frame_current": "info", "time_marker": "gold",
    "time_marker_selected": "accent", "time_marker_line": "gold",
    "time_marker_line_selected": "accent", "keyframe": "fg2",
    "keyframe_selected": "accent", "keyframe_extreme": "warn",
    "keyframe_extreme_selected": "warn", "keyframe_generated": "fg3",
    "keyframe_generated_selected": "fg2", "long_key": "fg3",
    "long_key_selected": "accent", "interpolation_line": "fg3",
    "preview_range": "fg3", "before_current_frame": "fg3",
    "after_current_frame": "fg3", "simulated_frames": "info", "summary": "fg2",
    "channel": "fg2", "channel_group": "fg3", "channel_group_active": "accent",
    "channels": "fg3", "channels_sub": "fg3",
    "active_channels_group": "accent", "dopesheet_channel": "fg2",
    "dopesheet_subchannel": "fg3", "nla_track": "raised",
    "active_action": "accent", "active_action_unset": "fg3", "tweak": "accent",
    "tweak_duplicate": "warn", "act_spline": "fg3",
    "active_modifier": "accent", "draw_action": "accent",
    # curve handles
    "handle_free": "fg3", "handle_auto": "fg2", "handle_vect": "fg2",
    "handle_align": "fg2", "handle_auto_clamped": "fg2",
    "handle_sel_free": "accent", "handle_sel_auto": "accent",
    "handle_sel_vect": "accent", "handle_sel_align": "accent",
    "handle_sel_auto_clamped": "accent", "handle_vertex": "fg2",
    "handle_vertex_select": "accent", "lastsel_point": "gold",
    "paint_curve_pivot": "gold", "paint_curve_handle": "fg3",
    # image, clip, sequencer, file browser
    "scope_back": "space_back", "preview_back": "space_back",
    "preview_stitch_active": "accent", "preview_stitch_stitchable": "accent",
    "preview_stitch_unstitchable": "err", "preview_stitch_vert": "accent",
    "uv_shadow": "fg3", "metadatabg": "raised", "metadatatext": "fg",
    "selected_file": "accent", "selected_strip": "accent",
    "selected_text": "accent", "text_strip_cursor": "fg",
    "marker": "gold", "selected_marker": "accent", "active_marker": "accent",
    "disabled_marker": "fg3", "locked_marker": "fg3", "marker_outline": "border",
    "path_before": "fg3", "path_after": "fg3", "path_keyframe_before": "fg2",
    "path_keyframe_after": "fg2",
    # info bar and console
    "info_selected": "accent", "info_selected_text": "fg",
    "info_operator": "raised", "info_operator_text": "fg",
    "info_property": "raised", "info_property_text": "fg",
    "info_debug": "raised", "info_debug_text": "fg3",
    "info_error_text": "err", "info_warning_text": "warn",
    "info_info_text": "info", "info_error": "err", "info_warning": "warn",
    "info_info": "info", "cursor": "fg", "line_error": "err",
    "line_info": "info", "line_input": "fg", "line_output": "text",
    "select": "sel", "line_numbers": "line_numbers",
    "line_numbers_background": "space_back",
    # syntax (mirrors the IDEA schemes)
    "syntax_string": "syn_string",
    "syntax_numbers": "syn_number", "syntax_comment": "syn_comment",
    "syntax_builtin": "syn_builtin", "syntax_reserved": "syn_keyword",
    "syntax_special": "syn_special", "syntax_symbols": "syn_symbols",
    "syntax_preprocessor": "syn_preprocessor",
    # widget state colours
    "error": "err", "warning": "warn", "success": "info", "info": "info",
    "inner_key": "gold", "inner_key_sel": "gold",
    # interface extras
    "axis_x": "axis_x", "axis_y": "axis_y", "axis_z": "axis_z",
    "axis_w": "axis_w", "gizmo_hi": "fg", "gizmo_primary": "gold",
    "gizmo_secondary": "info", "gizmo_view_align": "fg", "gizmo_a": "rgb_a",
    "gizmo_b": "rgb_b", "icon_scene": "fg", "icon_collection": "fg",
    "icon_object": "gold", "icon_object_data": "info",
    "icon_modifier": "accent", "icon_shading": "err", "icon_folder": "gold",
    "icon_autokey": "err", "icon_border_intensity": "fg3",
    # attributes only older or newer versions carry -- mapped so every version
    # gets a themed value instead of Blender's default
    "edge_facesel": "accent", "face_dot": "gold", "normal": "info",
    "editmesh_active": "fg", "camera_path": "fg3", "camera_passepartout": "veil",
    "view_overlay": "veil", "text_keyframe": "gold", "active_strip": "fg",
    "match": "gold", "link": "info", "panel_active": "accent",
    "header_back": "panel", "time_scrub_background": "panel",
    "value_sliders": "raised", "view_sliders": "raised",
    "window_sliders": "raised", "channels_region": "panel",
    "channels_selected": "accent", "channel_selected": "accent",
    "vertex_active": "gold",
    "selected_text": "on_accent", "text_selected": "on_accent",
    "scene_strip_range": "raised",
}

# keep the hue, restate the tone (Blender's semantic rainbow)
TONE_ROLES = {
    "crease", "seam", "sharp", "bevel", "freestyle", "freestyle_edge_mark",
    "freestyle_face_mark", "shader_node", "output_node", "input_node",
    "color_node", "converter_node", "vector_node", "texture_node",
    "geometry_node", "attribute_node", "matte_node", "filter_node",
    "script_node", "distor_node", "frame_node", "group_node",
    "group_socket_node", "layout_node", "pattern_node", "repeat_zone",
    "simulation_zone", "closure_zone", "foreach_geometry_element_zone",
    "preview_stitch_edge", "preview_stitch_face", "text_strip", "color_strip",
    "audio_strip", "effect_strip", "image_strip", "movie_strip",
    "movieclip_strip", "scene_strip", "mask_strip", "meta_strip",
    "meta_strips", "meta_strips_selected", "sound_strips",
    "sound_strips_selected", "strips", "strips_selected", "transition_strips",
    "transition_strips_selected", "keyframe_breakdown",
    "keyframe_breakdown_selected", "keyframe_jitter", "keyframe_jitter_selected",
    "keyframe_moving_hold", "keyframe_moving_hold_selected", "keyframe_movehold",
    "keyframe_movehold_selected", "inner_anim", "inner_anim_sel",
    "inner_driven", "inner_driven_sel", "inner_overridden",
    "inner_overridden_sel", "inner_changed", "inner_changed_sel",
    # old spellings of the semantic rainbow: their reference hue is identical to
    # the new name, so both versions end up the same colour
    "edge_seam", "edge_sharp", "edge_crease", "edge_bevel", "vertex_bevel",
    "wire_inner", "transition_strip", "face_retopology",
    "anim_interpolation_constant", "anim_interpolation_linear",
    "anim_interpolation_other",
}
# array members are built by ramp()/tone() rather than looked up
ARRAY_ATTRS = {"normal", "select", "active", "color"}
# keyframe_border is an outline for the selected key: keep it near the selection
TONE_OVERRIDE = {"keyframe_border": "accent", "keyframe_border_selected": "accent"}


def roles_for(p):
    # every role keeps its leading '#': these values go straight into the XML,
    # and a bare "e2e0de" is not a colour Blender can parse
    return {k: "#" + hexv(p[k]).lower() for k in
         ("space_back", "panel", "raised", "hover", "border", "fg", "fg2", "fg3",
          "text", "text_hi", "sel", "accent", "gold", "info", "err", "warn",
          "on_accent", "wire", "wire_edit", "vertex", "axis_x", "axis_y",
          "axis_z", "axis_w", "rgb_a", "rgb_b", "syn_keyword", "syn_string",
          "syn_number", "syn_comment", "syn_reserved", "syn_builtin",
          "syn_special", "syn_symbols", "syn_preprocessor", "line_numbers",
          "veil")
         if k in p}


ARRAY_TAGS = ("ThemeCollectionColor", "ThemeStripColor")


def colour_for(name, ref_value, tag, roles, dark, report):
    if name in TONE_OVERRIDE:
        return with_alpha(roles[TONE_OVERRIDE[name]], alpha_of(ref_value))
    # the collection and strip ramps are one hue per entry: keep the hue, let the
    # tone pass restate it, and do not report them as unmapped
    if tag in ARRAY_TAGS and name == "color":
        return tone(ref_value, dark)
    if name in TONE_ROLES:
        return tone(ref_value, dark)
    role = DIRECT.get(name)
    if role and role in roles:
        return with_alpha(roles[role], alpha_of(ref_value))
    if role:
        report.setdefault("missing_role", []).append(f"{tag}.{name} -> {role}")
        return tone(ref_value, dark)
    report.setdefault("unmapped", []).append(f"{tag}.{name}")
    return tone(ref_value, dark)


# ------------------------------------------------------------------ convert --
def convert(node, roles, dark, report):
    """Rewrite one reference element into themed attributes, recursively."""
    if node.tag == "ThemeBoneColorSet":
        # normal -> select -> active is a brightness ramp in Blender's own
        # palettes, and it has to survive the re-toning: toning the three
        # independently would flatten them onto the same clamped value, so the
        # brighter two are derived from the first.

        body = hexv(node.attrib.get("normal", "#808080"))
        r, g, b = (int(body[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if dark:
            s, v0, vmax = min(max(s, 0.45), 0.85), min(max(v, 0.45), 0.70), 0.86
        else:
            s, v0, vmax = min(max(s, 0.50), 0.90), min(max(v, 0.40), 0.60), 0.70
        ramp = {
            "normal": hsv_hex(h, s, v0),
            "select": hsv_hex(h, s, min(vmax, v0 + 0.08)),
            "active": hsv_hex(h, min(1.0, s * 1.05), min(vmax, v0 + 0.16)),
        }
        attrs = [(n, with_alpha(ramp[n], alpha_of(val)) if n in ramp else val)
                 for n, val in node.attrib.items() if n not in DROP_ATTRS]
        return (node.tag, attrs, [convert(c, roles, dark, report) for c in node])

    attrs = []
    for name, ref_value in node.attrib.items():
        if name in DROP_ATTRS:
            continue
        if hexv(ref_value):
            attrs.append((name, colour_for(name, ref_value, node.tag, roles,
                                           dark, report)))
        else:
            attrs.append((name, ref_value))
    kids = [convert(c, roles, dark, report) for c in node]
    return (node.tag, attrs, kids)


def emit(tree, name):
    """Serialise the converted tree.

    `tree` IS the <bpy> root, so it is written at depth 0. Prepending a wrapper
    line here nests <bpy> inside <bpy>, which Blender tolerates because it finds
    Theme recursively -- but it is not the format Blender's own presets use.
    """
    return "\n".join(indent_lines(tree[0], tree[1], tree[2], 0)) + "\n"


def indent_lines(tag, attrs, children, depth):
    pad = "  " * depth
    out = [f"{pad}<{tag}"]
    for n, v in attrs:
        out.append(f'{pad}  {n}="{v}"')
    out.append(f"{pad}  >")
    for c in children:
        out.extend(indent_lines(c[0], c[1], c[2], depth + 1))
    out.append(f"{pad}</{tag}>")
    return out


def floor_syntax(tree, report, floor=4.5, low_floor=3.9):
    """Pull the text editor's syntax colours up to a readable contrast.

    Most of them come straight from the IDEA schemes and were already verified
    against this exact background, but the ones built by tone() (reserved words,
    for instance) are derived from Blender's own value and can land just short.
    Only lightness moves, so hue and saturation survive.
    """
    changed = []
    for node in walk_nodes(tree):
        if node[0] != "ThemeTextEditor":
            continue
        attrs = dict(node[1])
        back = attrs.get("line_numbers_background") or "#000000"
        fixed = []
        for name, value in node[1]:
            if not (isinstance(value, str) and value.startswith("#")
                    and name.startswith("syntax_")):
                fixed.append((name, value))
                continue
            target = low_floor if name == "syntax_comment" else floor
            new = adjust(value, back, target)
            if new.lower() != value.lower():
                changed.append(f"{name} {value} -> {new} on {back}")
            fixed.append((name, new))
        node[1][:] = fixed
    if changed:
        report.setdefault("floored", []).extend(changed)
    return changed


# ---------------------------------------------------------------- RNA probes --
def walk_nodes(node):
    """Yield every node of a (tag, attrs, kids) tree, depth first."""
    yield node
    for c in node[2]:
        yield from walk_nodes(c)


def probes(tree):
    """(rna_path, attribute, expected_hex) for every colour written.

    The RNA path mirrors the XML wrapper names: <view_3d><ThemeView3D ..> is
    theme.view_3d, a nested <space><ThemeSpaceGradient ..> is view_3d.space, and
    a repeated wrapper such as <bone_color_sets><ThemeBoneColorSet ..> is
    bone_color_sets[0], bone_color_sets[1], ...
    """
    out = []

    def walk_type(node, path):
        for n, v in node[1]:
            if hexv(v):
                out.append((path, n, v))
        for wrapper in node[2]:
            walk_wrapper(wrapper, path)

    def walk_wrapper(wrapper, prefix):
        base = f"{prefix}.{wrapper[0]}" if prefix else wrapper[0]
        groups = {}
        for c in wrapper[2]:
            groups.setdefault(c[0], []).append(c)
        for group in groups.values():
            if len(group) > 1:
                for i, c in enumerate(group):
                    walk_type(c, f"{base}[{i}]")
            else:
                walk_type(group[0], base)

    for child in tree[2]:
        if child[0] == "ThemeStyle":
            for wrapper in child[2]:
                walk_wrapper(wrapper, "style")
        else:
            for wrapper in child[2]:
                walk_wrapper(wrapper, "")
    return out


# --------------------------------------------------------------- validation --
def validate_contrast(tree, p, problems):
    dark = p["dark"]
    floor_ui = 2.6 if dark else 2.8
    floor_syn = 4.5

    nodes = list(walk_nodes(tree))

    def find(tag):
        return [n for n in nodes if n[0] == tag]

    def get(node, attr):
        for n, v in node[1]:
            if n == attr:
                return v
        return None

    for node in find("ThemeSpaceGeneric") + find("ThemeSpaceGradient"):
        back = get(node, "back") or p["space_back"]
        for fg_attr, floor in (("text", floor_ui), ("title", floor_ui),
                               ("header_text", floor_ui), ("text_hi", floor_ui)):
            fg = get(node, fg_attr)
            if fg and contrast(fg, back) < floor:
                problems.append(f"{node[0]}.{fg_attr} {fg} on back {back} = "
                                f"{contrast(fg, back)} < {floor}")
        hdr = get(node, "header")
        if hdr and get(node, "header_text"):
            c = contrast(get(node, "header_text"), hdr)
            if c < floor_ui:
                problems.append(f"{node[0]}.header_text on header = {c} < {floor_ui}")

    for node in find("ThemeWidgetColors"):
        for txt, bg in (("text", "inner"), ("text_sel", "inner_sel")):
            f, b = get(node, txt), get(node, bg)
            if f and b and contrast(f, b) < floor_ui:
                problems.append(f"{node[0]}.{txt} {f} on {bg} {b} = "
                                f"{contrast(f, b)} < {floor_ui}")

    low_floor = {"syntax_comment": 3.9}
    te = find("ThemeTextEditor")
    if te:
        back = get(te[0], "line_numbers_background") or p["space_back"]
        for n, v in te[0][1]:
            if n.startswith("syntax_") and hexv(v):
                floor = low_floor.get(n, floor_syn)
                c = contrast(v, back)
                if c < floor:
                    problems.append(f"ThemeTextEditor.{n} {v} on {back} = {c} < {floor}")

    for node in find("ThemeConsole"):
        back = p["space_back"]
        for n, v in node[1]:
            if n.startswith("line_") and hexv(v) and contrast(v, back) < floor_syn:
                problems.append(f"ThemeConsole.{n} {v} on {back} = "
                                f"{contrast(v, back)} < {floor_syn}")


MANIFEST = """schema_version = "1.0.0"

id = "{ext_id}"
version = "1.0.0"
name = "{name}"
tagline = "{tagline}"
maintainer = "kb"
type = "theme"

tags = [{tags}]

# The structure, the attribute names and every non-colour value in the theme come
# from Blender's own presets and theme defaults, so the result is derived from
# GPL-licensed Blender data.
license = [
  "SPDX:GPL-2.0-or-later",
]

blender_version_min = "{min_version}"
"""


# Zip entries carry a timestamp, so a rebuild would otherwise change the bytes of
# identical content. Pinning it makes the packaging reproducible.
ZIP_DATE = (2026, 9, 18, 12, 0, 0)


def package_extensions():
    """One installable Blender extension per theme.

    Blender 4.2+ installs themes as extensions: a zip holding blender_manifest.toml
    and the theme XML at its root. That beats copying files into the scripts
    directory -- Preferences > Get Extensions > Install from Disk (or just drag the
    zip onto the window) is enough.
    """
    import zipfile
    made = []
    for name in THEME_NAMES:
        xml_name = FILE_OF[name]
        ext_id = xml_name[:-4]
        zip_path = os.path.join(OUT, ext_id + ".zip")
        manifest = MANIFEST.format(
            ext_id=ext_id, name=name,
            tagline=("Dark theme -- " if ap.PALETTES[name]["dark"] else
                     "Light theme -- ") + "Kurumi Tokisaki / Hatsune Miku palettes",
            tags='"Dark"' if ap.PALETTES[name]["dark"] else '"Light"',
            min_version="4.5.0")
        with zipfile.ZipFile(zip_path, "w") as z:
            for arcname, data in (("blender_manifest.toml", manifest.encode("utf-8")),
                                  (xml_name, open(os.path.join(OUT, xml_name),
                                                  "rb").read())):
                info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, data)
        made.append(zip_path)
    return made


def main():
    os.makedirs(OUT, exist_ok=True)
    refs = find_references()
    print("references found:")
    for ref in refs:
        print(f"   {ref['version']}: {ref['light']}")
        print(f"   {ref['version']}: {ref['dark']}")
    if not refs:
        sys.exit("no usable references")

    problems, reports = [], {}
    built = {}
    for variant in ("light", "dark"):
        skel, used = skeleton(variant)
        n_attrs = sum(len(e.attrib) for e in skel.iter())
        print(f"\n{variant} skeleton from versions {used}: "
              f"{len(list(skel.iter()))} elements, {n_attrs} attributes")
        for name in THEME_NAMES:
            p = palette(name)
            if p["dark"] != (variant == "dark"):
                continue
            report = {}
            tree = convert(skel, roles_for(p), p["dark"], report)
            body = emit(tree, name)
            path = os.path.join(OUT, FILE_OF[name])
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
            ET.fromstring(body.encode("utf-8"))          # well-formedness
            pr = probes(tree)
            with open(os.path.join(OUT, FILE_OF[name] + ".probe.json"), "w",
                      encoding="utf-8", newline="\n") as f:
                json.dump(pr, f)
            floor_syntax(tree, report)
            validate_contrast(tree, p, problems)
            reports[name] = report
            built[name] = (path, len(body), len(pr))
            print(f"  {FILE_OF[name]:28s} {len(body):8,} bytes  "
                  f"{len(pr):4d} colours probed")

    print("\nunmapped colour attributes (kept Blender's hue, theme tone):")
    for name, report in reports.items():
        un = sorted(set(report.get("unmapped", [])))
        mr = sorted(set(report.get("missing_role", [])))
        if un:
            print(f"  {name}: {len(un)} unmapped")
            for u in un:
                print(f"     {u}")
        if mr:
            print(f"  {name}: role not in palette: {mr}")
        fl = sorted(set(report.get("floored", [])))
        if fl:
            print(f"  {name}: {len(fl)} syntax colour(s) nudge for readability:")
            for f in fl:
                print(f"     {f}")

    print("\ncontrast problems:")
    if problems:
        for pr in problems:
            print("   ", pr)
    else:
        print("    none")

    if problems:
        raise SystemExit(1)

    print("\nextension packages:")
    import zipfile
    for path in package_extensions():
        base = os.path.basename(path)
        expected = {base[:-4] + ".xml", "blender_manifest.toml"}
        with zipfile.ZipFile(path) as z:
            entries = set(z.namelist())
        if entries != expected:
            problems.append(f"{base}: unexpected contents {sorted(entries)}")
        print(f"  {base:32s} {os.path.getsize(path):7,d} bytes  "
              f"= {sorted(entries)}")
    if problems:
        raise SystemExit(1)
    print("\nall blender theme checks passed")


if __name__ == "__main__":
    main()
