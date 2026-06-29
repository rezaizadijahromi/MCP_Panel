"""
Splitter silencer design engine — params in, drawing + figures out.

Geometry: W/8 splitter | W/4 air | W/4 splitter | W/4 air | W/8 splitter
(50% open-area ratio by construction; airway gap = W/4)

Usage:
    python engine.py --length 1200 --width 1000 --height 1000
    from engine import generate, DEFAULTS
"""
import argparse
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: registers 3d

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")

C_AIR = 343_000.0  # speed of sound, mm/s

DEFAULTS = {
    "length_mm": 1500.0,   # splitter length (acoustic length, airflow direction)
    "width_mm":  1000.0,   # cross-section width  (baffles are laid out across this)
    "height_mm": 1000.0,   # cross-section height (splitters span the full height)
}


# ----------------------------------------------------------------------
# 1. BAFFLE LAYOUT
# ----------------------------------------------------------------------
def _layout(W):
    """Return the left->right spans across the width as (kind, x0, x1) plus the
    key thicknesses. Fixed build-up: W/8 + W/4 + W/4 + W/4 + W/8."""
    s_side = W / 8.0          # side splitters (half-thickness)
    s_mid = W / 4.0           # middle splitter (full)
    gap = W / 4.0             # each airway gap
    spans = [
        ("splitter", 0.0,              s_side),
        ("air",      s_side,           s_side + gap),
        ("splitter", s_side + gap,     s_side + gap + s_mid),
        ("air",      s_side + gap + s_mid, W - s_side),
        ("splitter", W - s_side,       W),
    ]
    return spans, s_side, s_mid, gap


# ----------------------------------------------------------------------
# 2. PHYSICS
# ----------------------------------------------------------------------
def _derive(p):
    """Derive geometry + acoustic figures from the input parameters."""
    L = float(p["length_mm"])
    W = float(p["width_mm"])
    H = float(p["height_mm"])

    spans, s_side, s_mid, gap = _layout(W)
    solid = 2 * s_side + s_mid                 # total splitter material across W
    open_width = W - solid                     # total airway across W
    open_ratio = open_width / W                # == 0.5 by construction

    default_gap = DEFAULTS["width_mm"] / 4.0
    peak_TL = (L / 30.0) * (default_gap / gap)
    peak_TL = round(peak_TL, 1)

    # Peak band is set by the airway gap (half-wavelength resonance).
    f_peak = round(C_AIR / (2.0 * gap) / 10.0) * 10.0   # Hz

    return {
        "duct_width_mm": round(W, 1),
        "duct_height_mm": round(H, 1),
        "splitter_side_mm": round(s_side, 1),
        "splitter_mid_mm": round(s_mid, 1),
        "airway_gap_mm": round(gap, 1),
        "open_area_ratio": round(open_ratio, 3),
        "peak_TL_dB": peak_TL,
        "peak_freq_hz": f_peak,
        "_spans": spans,
    }


def _tl_curve(f_peak, peak_TL):
    """A smooth TL-vs-frequency curve peaking at (f_peak, peak_TL)."""
    f = np.logspace(np.log10(50), np.log10(5000), 240)
    sigma = 0.85
    tl = peak_TL * np.exp(-(np.log(f / f_peak) ** 2) / (2 * sigma ** 2))
    return f, np.clip(tl, 0, None)


def _merge(params):
    """Fill any missing parameter from DEFAULTS and coerce to numbers."""
    p = dict(DEFAULTS)
    for k, v in (params or {}).items():
        if k in p and v is not None:
            p[k] = v
    for k in ("length_mm", "width_mm", "height_mm"):
        p[k] = float(p[k])
    return p


# ----------------------------------------------------------------------
# 3. DRAWING
# ----------------------------------------------------------------------
def _cuboid_faces(x0, x1, y0, y1, z0, z1):
    """The 6 faces of an axis-aligned box, ordered:
    bottom, top, front(y0), back(y1), left(x0), right(x1)."""
    c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return [
        [c[0], c[1], c[2], c[3]],   # bottom (z0)
        [c[4], c[5], c[6], c[7]],   # top    (z1)
        [c[0], c[1], c[5], c[4]],   # front  (y0)
        [c[3], c[2], c[6], c[7]],   # back   (y1)
        [c[0], c[3], c[7], c[4]],   # left   (x0)
        [c[1], c[2], c[6], c[5]],   # right  (x1)
    ]


def _draw_iso(ax, p, d):
    """Isometric 3D view of the duct + baffles, with L/W/H dimensions."""
    L, W, H = p["length_mm"], p["width_mm"], p["height_mm"]
    spans = d["_spans"]

    ax.set_axis_off()

    # Outer duct envelope as a light wireframe (no solid casing / mounting walls).
    corners = [(0, 0, 0), (W, 0, 0), (W, L, 0), (0, L, 0),
               (0, 0, H), (W, 0, H), (W, L, H), (0, L, H)]
    box_edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                 (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    for a, b in box_edges:
        ax.plot([corners[a][0], corners[b][0]],
                [corners[a][1], corners[b][1]],
                [corners[a][2], corners[b][2]],
                color="#465260", lw=1.0)

    # Splitters as shaded solid slabs (top lighter, sides darker -> 3d feel).
    face_cols = ["#3c454f", "#8d9aa8", "#647284", "#56616f", "#4a545f", "#414b55"]
    for kind, x0, x1 in spans:
        if kind != "splitter":
            continue
        pc = Poly3DCollection(_cuboid_faces(x0, x1, 0, L, 0, H),
                              facecolors=face_cols, edgecolors="#222",
                              linewidths=0.4)
        pc.set_zsort("average")
        ax.add_collection3d(pc)

    # --- dimension lines + labels -----------------------------------------
    red = "#c0392b"
    ink = "#26333f"
    ox = -0.12 * W      # offset to the left  (for H)
    oy = -0.14 * L      # offset to the front (for W)
    ax.plot([0, W], [oy, oy], [0, 0], color=ink, lw=1.4)
    ax.text(W / 2, oy, -0.06 * H, f"W = {W:.0f} mm",
            color=ink, ha="center", va="top")
    ax.plot([ox, ox], [oy, oy], [0, H], color=ink, lw=1.4)
    ax.text(ox * 1.18, oy, H / 2, f"H = {H:.0f} mm",
            color=ink, ha="center", va="center", rotation=90)
    lx = W * 1.06
    ax.plot([lx, lx], [0, L], [0, 0], color=red, lw=1.8)
    ax.text(lx * 1.02, L / 2, -0.06 * H, f"L = {L:.0f} mm",
            color=red, weight="bold", ha="left", va="top")

    ax.set_xlim(-0.22 * W, W * 1.30)
    ax.set_ylim(-0.20 * L, L * 1.04)
    ax.set_zlim(0, H * 1.05)
    ax.set_box_aspect((1.30 * W, 1.24 * L, 1.05 * H))
    ax.view_init(elev=22, azim=-58)
    ax.set_title("Isometric view  (airflow along L)", pad=-2)


def _draw(p, d, out_path):
    f, tl = _tl_curve(d["peak_freq_hz"], d["peak_TL_dB"])
    L, W, H = p["length_mm"], p["width_mm"], p["height_mm"]

    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.45, 1.0],
                          height_ratios=[1.0, 1.0], hspace=0.30, wspace=0.12)
    fig.suptitle("Splitter Silencer — revised drawing", fontsize=15, weight="bold")

    ax3d = fig.add_subplot(gs[:, 0], projection="3d")
    _draw_iso(ax3d, p, d)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.semilogx(f, tl, color="#1f6fb2", lw=2)
    ax2.scatter([d["peak_freq_hz"]], [d["peak_TL_dB"]], color="#c0392b", zorder=5)
    ax2.annotate(f"peak {d['peak_TL_dB']:.0f} dB @ {d['peak_freq_hz']:.0f} Hz",
                 (d["peak_freq_hz"], d["peak_TL_dB"]),
                 textcoords="offset points", xytext=(8, -4), color="#c0392b")
    ax2.set_xlabel("frequency (Hz)")
    ax2.set_ylabel("transmission loss (dB)")
    ax2.set_title("Transmission loss")
    ax2.grid(True, which="both", alpha=0.3)
    ax2.set_ylim(0, max(10, d["peak_TL_dB"] * 1.2))

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis("off")
    rows = [
        ("Splitter length", f"{L:.0f} mm"),
        ("Cross-section", f"{W:.0f} x {H:.0f} mm"),
        ("Baffles", "W/8 + W/4 + W/8 solid"),
        ("Airway gap", f"{d['airway_gap_mm']:.0f} mm (W/4)"),
        ("Open-area ratio", f"{d['open_area_ratio']:.0%}"),
        ("Peak TL", f"{d['peak_TL_dB']:.0f} dB @ {d['peak_freq_hz']:.0f} Hz"),
    ]
    y = 0.95
    ax3.text(0.0, y, "Key figures", weight="bold", fontsize=12)
    y -= 0.14
    for label, val in rows:
        ax3.text(0.0, y, label, fontsize=11)
        ax3.text(1.0, y, val, fontsize=11, ha="right", weight="bold")
        y -= 0.13

    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------
# 4. ENTRY POINT
# ----------------------------------------------------------------------
def generate(params, out_dir=None, write_summary=False):
    """Generate the drawing for `params` (a dict). Returns a summary dict
    including the drawing path. Missing params fall back to DEFAULTS."""
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    p = _merge(params)
    d = _derive(p)

    tag = f"{int(p['length_mm'])}x{int(p['width_mm'])}x{int(p['height_mm'])}"
    png = os.path.join(out_dir, f"drawing_{tag}.png")
    _draw(p, d, png)

    public = {k: v for k, v in d.items() if not k.startswith("_")}
    summary = {**p, **public, "drawing_png": png,
               "drawing_file": os.path.basename(png)}
    if write_summary:
        with open(os.path.join(out_dir, f"summary_{tag}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
    return summary


def _load_cli_params(argv):
    ap = argparse.ArgumentParser(description="Splitter silencer design engine")
    ap.add_argument("json", nargs="?", help="path to a params JSON file")
    ap.add_argument("--length", type=float, help="splitter length in mm")
    ap.add_argument("--width", type=float, help="cross-section width in mm")
    ap.add_argument("--height", type=float, help="cross-section height in mm")
    a = ap.parse_args(argv)

    params = {}
    if a.json:
        with open(a.json, encoding="utf-8") as fh:
            params.update(json.load(fh))
    if a.length is not None: params["length_mm"] = a.length
    if a.width  is not None: params["width_mm"] = a.width
    if a.height is not None: params["height_mm"] = a.height
    return params


if __name__ == "__main__":
    res = generate(_load_cli_params(sys.argv[1:]), write_summary=True)
    print("Generated:", res["drawing_file"])
    for k in ("length_mm", "width_mm", "height_mm", "airway_gap_mm",
              "open_area_ratio", "peak_freq_hz", "peak_TL_dB"):
        print(f"  {k}: {res[k]}")
