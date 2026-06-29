"""
Acoustic panel design engine — params in, drawing + figures out.

Layer build-up: incident sound → rockwool (absorber) | EPDM (damping) | steel (backing)

Usage:
    python engine_panel.py --rockwool 75
    from engine_panel import generate, DEFAULTS
"""
import argparse
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")

C_AIR = 343_000.0     # speed of sound, mm/s
STEEL_DENSITY = 7850.0  # kg/m^3, for the steel surface-mass figure

# Baseline panel. The stratification (through-thickness layer build-up) is what
# drives the acoustic performance; the face size is cosmetic / for the BOM.
DEFAULTS = {
    "panel_width_mm":   600.0,   # panel face width
    "panel_height_mm": 1200.0,   # panel face height
    "rockwool_mm":       50.0,   # porous absorber (rockwool) facing the sound
    "epdm_mm":            6.0,   # viscoelastic damping membrane
    "steel_mm":           2.0,   # rigid steel mass backing
}


# ----------------------------------------------------------------------
# 1. DETERMINISTIC PHYSICS  (simplified backed-absorber model)
# ----------------------------------------------------------------------
def _derive(p):
    rockwool = float(p["rockwool_mm"])
    epdm = float(p["epdm_mm"])
    steel = float(p["steel_mm"])

    total_depth = rockwool + epdm + steel
    d_eff = rockwool                         # porous depth in front of the rigid steel

    # Peak absorption near the quarter-wavelength resonance of the porous layer.
    f_peak = round(C_AIR / (4.0 * d_eff) / 10.0) * 10.0   # Hz

    # More rockwool -> higher/broader peak; the EPDM adds a little damping.
    alpha_peak = min(0.99, 0.55 + rockwool / 200.0 + epdm / 80.0)
    alpha_peak = round(alpha_peak, 2)

    # NRC = mean absorption at the four standard octave bands, to nearest 0.05.
    bands = [250.0, 500.0, 1000.0, 2000.0]
    a_bands = [_alpha_at(f, f_peak, alpha_peak) for f in bands]
    nrc = round(round((sum(a_bands) / len(a_bands)) / 0.05) * 0.05, 2)

    steel_surface_mass = round(steel / 1000.0 * STEEL_DENSITY, 1)

    return {
        "total_depth_mm": round(total_depth, 1),
        "resonant_depth_mm": round(d_eff, 1),
        "peak_freq_hz": f_peak,
        "alpha_peak": alpha_peak,
        "NRC": nrc,
        "steel_surface_mass_kg_m2": steel_surface_mass,
    }


def _alpha_at(f, f_peak, alpha_peak, sigma=1.1):
    return float(np.clip(alpha_peak * np.exp(-(np.log(f / f_peak) ** 2) /
                                             (2 * sigma ** 2)), 0, 0.99))


def _alpha_curve(f_peak, alpha_peak):
    f = np.logspace(np.log10(50), np.log10(5000), 240)
    a = alpha_peak * np.exp(-(np.log(f / f_peak) ** 2) / (2 * 1.1 ** 2))
    return f, np.clip(a, 0, 0.99)


def _merge(params):
    p = dict(DEFAULTS)
    for k, v in (params or {}).items():
        if k in p and v is not None:
            p[k] = v
    for k in p:
        p[k] = float(p[k])
    return p


# ----------------------------------------------------------------------
# 2. DRAWING
# ----------------------------------------------------------------------
def _draw(p, d, out_path):
    rockwool, epdm, steel = p["rockwool_mm"], p["epdm_mm"], p["steel_mm"]
    W, H = p["panel_width_mm"], p["panel_height_mm"]
    f, a = _alpha_curve(d["peak_freq_hz"], d["alpha_peak"])

    fig = plt.figure(figsize=(12, 7.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.4, 1.0],
                          height_ratios=[1.0, 1.0], hspace=0.35, wspace=0.18)
    fig.suptitle("Acoustic Panel — stratified build-up", fontsize=15, weight="bold")

    ax1 = fig.add_subplot(gs[:, 0])
    layers = [
        ("Rockwool\n(absorber)", rockwool, "#e6c84f", "xx"),
        ("EPDM\n(damping)",      epdm,     "#2f2f33", ""),
        ("Steel sheet\n(backing)", steel,  "#b8c0c8", "//"),
    ]
    total = sum(t for _, t, _, _ in layers) or 1.0
    floor = 0.18 * total                      # minimum display width per layer
    disp = [max(t, floor) for _, t, _, _ in layers]
    disp_total = sum(disp)
    bar_h = disp_total * 0.55
    x = 0.0
    for idx, ((name, t, color, hatch), w) in enumerate(zip(layers, disp)):
        if t <= 0:
            continue
        ax1.add_patch(Rectangle((x, 0), w, bar_h, facecolor=color,
                                edgecolor="#222", hatch=hatch, linewidth=1.0))
        ax1.annotate("", (x, -bar_h * 0.08), (x + w, -bar_h * 0.08),
                     arrowprops=dict(arrowstyle="<->", color="#26333f", lw=0.9))
        ax1.text(x + w / 2, -bar_h * 0.15, f"{t:.0f} mm", ha="center", va="top",
                 fontsize=9, color="#26333f")
        label_y = bar_h * (1.30 if idx % 2 else 1.06)
        ax1.plot([x + w / 2, x + w / 2], [bar_h * 1.01, label_y - bar_h * 0.02],
                 color="#9aa3ad", lw=0.7)
        ax1.text(x + w / 2, label_y, name, ha="center", va="bottom", fontsize=9)
        x += w
    ax1.annotate("incident\nsound", (0, bar_h * 0.5),
                 (-disp_total * 0.13, bar_h * 0.5), ha="center", va="center",
                 fontsize=10, color="#c0392b",
                 arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=2))
    ax1.set_xlim(-disp_total * 0.22, disp_total * 1.04)
    ax1.set_ylim(-bar_h * 0.32, bar_h * 1.62)
    ax1.set_aspect("equal")
    ax1.axis("off")
    ax1.set_title(f"Cross-section  (total depth {d['total_depth_mm']:.0f} mm, "
                  f"schematic — not to scale)", fontsize=10.5)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.semilogx(f, a, color="#1f6fb2", lw=2)
    ax2.scatter([d["peak_freq_hz"]], [d["alpha_peak"]], color="#c0392b", zorder=5)
    ax2.annotate(f"peak a={d['alpha_peak']:.2f} @ {d['peak_freq_hz']:.0f} Hz",
                 (d["peak_freq_hz"], d["alpha_peak"]),
                 textcoords="offset points", xytext=(6, -12), color="#c0392b")
    ax2.set_xlabel("frequency (Hz)")
    ax2.set_ylabel("absorption coefficient a")
    ax2.set_title("Sound absorption")
    ax2.grid(True, which="both", alpha=0.3)
    ax2.set_ylim(0, 1.05)

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis("off")
    rows = [
        ("Panel face", f"{W:.0f} x {H:.0f} mm"),
        ("Rockwool", f"{rockwool:.0f} mm"),
        ("EPDM", f"{epdm:.0f} mm"),
        ("Steel sheet", f"{steel:.0f} mm"),
        ("Total depth", f"{d['total_depth_mm']:.0f} mm"),
        ("Steel surface mass", f"{d['steel_surface_mass_kg_m2']:.1f} kg/m2"),
        ("Peak absorption", f"a {d['alpha_peak']:.2f} @ {d['peak_freq_hz']:.0f} Hz"),
        ("NRC", f"{d['NRC']:.2f}"),
    ]
    y = 0.97
    ax3.text(0.0, y, "Key figures", weight="bold", fontsize=12)
    y -= 0.115
    for label, val in rows:
        ax3.text(0.0, y, label, fontsize=10.5)
        ax3.text(1.0, y, val, fontsize=10.5, ha="right", weight="bold")
        y -= 0.108

    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------
# 3. PUBLIC ENTRY POINT
# ----------------------------------------------------------------------
def generate(params, out_dir=None, write_summary=False):
    """Generate the panel drawing for `params`. Returns a summary dict including
    the drawing path. Missing params fall back to DEFAULTS."""
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    p = _merge(params)
    d = _derive(p)

    tag = (f"{int(p['panel_width_mm'])}x{int(p['panel_height_mm'])}"
           f"_rw{int(p['rockwool_mm'])}_ep{int(p['epdm_mm'])}_st{int(p['steel_mm'])}")
    png = os.path.join(out_dir, f"panel_{tag}.png")
    _draw(p, d, png)

    summary = {**p, **d, "drawing_png": png, "drawing_file": os.path.basename(png)}
    if write_summary:
        with open(os.path.join(out_dir, f"panel_{tag}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
    return summary


def _load_cli_params(argv):
    ap = argparse.ArgumentParser(description="Stratified acoustic panel engine")
    ap.add_argument("json", nargs="?", help="path to a params JSON file")
    ap.add_argument("--width", type=float, help="panel face width in mm")
    ap.add_argument("--height", type=float, help="panel face height in mm")
    ap.add_argument("--rockwool", type=float, help="rockwool absorber thickness in mm")
    ap.add_argument("--epdm", type=float, help="EPDM damping thickness in mm")
    ap.add_argument("--steel", type=float, help="steel sheet thickness in mm")
    a = ap.parse_args(argv)

    params = {}
    if a.json:
        with open(a.json, encoding="utf-8") as fh:
            params.update(json.load(fh))
    if a.width    is not None: params["panel_width_mm"] = a.width
    if a.height   is not None: params["panel_height_mm"] = a.height
    if a.rockwool is not None: params["rockwool_mm"] = a.rockwool
    if a.epdm     is not None: params["epdm_mm"] = a.epdm
    if a.steel    is not None: params["steel_mm"] = a.steel
    return params


if __name__ == "__main__":
    res = generate(_load_cli_params(sys.argv[1:]), write_summary=True)
    print("Generated:", res["drawing_file"])
    for k in ("total_depth_mm", "resonant_depth_mm", "peak_freq_hz",
              "alpha_peak", "NRC", "steel_surface_mass_kg_m2"):
        print(f"  {k}: {res[k]}")
