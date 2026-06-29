"""Project store — maps project ids to (product type, current params)."""
from __future__ import annotations

import json
import os
import threading
import math
from dataclasses import dataclass, field, asdict

import engine          # silencer  : DEFAULTS, generate(params) -> summary
import engine_panel    # panel     : DEFAULTS, generate(params) -> summary

OUTPUT_DIR = engine.OUT_DIR
STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.json")

ENGINES = {
    "silencer": engine,
    "panel": engine_panel,
}

_PARAM_RULES = {
    "silencer": {
        "length_mm": "pos", "width_mm": "pos", "height_mm": "pos",
    },
    "panel": {
        "panel_width_mm": "pos", "panel_height_mm": "pos",
        "rockwool_mm": "pos",        
        "epdm_mm": "nonneg", "steel_mm": "nonneg",
    },
}


def _err(message: str) -> dict:
    """Structured failure the agent can read and relay (instead of an exception
    that would abort the whole chat turn)."""
    return {"ok": False, "error": message}


def _check_changes(product: str, changes: dict) -> str | None:
    """Return an error message if any requested value is unusable, else None."""
    rules = _PARAM_RULES[product]
    for k, v in changes.items():
        rule = rules.get(k)
        if rule is None:
            continue                   #ignore the unknown keys
        try:
            x = float(v)
        except (TypeError, ValueError):
            return f"{k} must be a number, got {v!r}"
        if not math.isfinite(x):
            return f"{k} must be a finite number, got {v!r}"
        if rule == "pos" and x <= 0:
            return f"{k} must be positive, got {x}"
        if rule == "nonneg" and x < 0:
            return f"{k} must not be negative, got {x}"
    return None




@dataclass
class Project:
    id: str
    name: str
    product: str                       # "silencer" | "panel"
    params: dict = field(default_factory=dict)


_SEED = [
    Project("sil-atrium", "Atrium silencer", "silencer", dict(engine.DEFAULTS)),
    Project("pan-studio", "Studio panel", "panel", dict(engine_panel.DEFAULTS)),
]

_lock = threading.Lock()
_projects: dict[str, Project] = {}


def _save() -> None:
    with open(STORE_FILE, "w", encoding="utf-8") as fh:
        json.dump([asdict(p) for p in _projects.values()], fh, indent=2)


def _load() -> None:
    if os.path.exists(STORE_FILE):
        with open(STORE_FILE, encoding="utf-8") as fh:
            for row in json.load(fh):
                _projects[row["id"]] = Project(**row)
    else:
        for p in _SEED:
            _projects[p.id] = p
        _save()


_load()


def list_projects() -> list[dict]:
    return [asdict(p) for p in _projects.values()]


def get_project(project_id: str) -> dict:
    return asdict(_require(project_id))


def update_silencer(project_id: str, length_mm=None, width_mm=None, height_mm=None) -> dict:
    return _apply(project_id, "silencer", {
        "length_mm": length_mm, "width_mm": width_mm, "height_mm": height_mm,
    })


def update_panel(project_id: str, panel_width_mm=None, panel_height_mm=None,
                 rockwool_mm=None, epdm_mm=None, steel_mm=None) -> dict:
    return _apply(project_id, "panel", {
        "panel_width_mm": panel_width_mm, "panel_height_mm": panel_height_mm,
        "rockwool_mm": rockwool_mm, "epdm_mm": epdm_mm, "steel_mm": steel_mm,
    })


def _require(project_id: str) -> Project:
    proj = _projects.get(project_id)
    if proj is None:
        raise KeyError(f"no project '{project_id}'. Known: {list(_projects)}")
    return proj

def _apply(project_id: str, expected_product: str, changes: dict) -> dict:
    with _lock:
        # 1. resolve the project (unknown id -> error the agent can relay)
        proj = _projects.get(project_id)
        if proj is None:
            return _err(f"no project '{project_id}'. Known: {list(_projects)}")

        # 2. product guard: don't run the silencer tool on a panel (or vice versa)
        if proj.product != expected_product:
            return _err(f"project '{project_id}' is a {proj.product}, not a "
                        f"{expected_product}; use the {proj.product} tool instead")

        # 3. keep only the parameters actually being changed
        clean = {k: v for k, v in changes.items() if v is not None}
        if not clean:
            return _err("no parameters given to change")

        # 4. guard the values BEFORE touching state or the engine, so a bad
        #    argument can neither crash the engine nor corrupt the store
        bad = _check_changes(proj.product, clean)
        if bad:
            return _err(bad)
        clean = {k: float(v) for k, v in clean.items()}

        # 5. regenerate from a candidate first; commit only if it succeeds, and
        #    wrap it so any unexpected engine error becomes a structured result
        #    rather than a crashed chat turn
        candidate = dict(proj.params)
        candidate.update(clean)
        try:
            summary = ENGINES[proj.product].generate(candidate, write_summary=False)
        except Exception as e:                       # noqa: surface, don't crash
            return _err(f"could not regenerate drawing: {e}")

        proj.params = candidate
        _save()

    return {
        "ok": True,
        "project": asdict(proj),
        "changed": clean,
        "summary": summary,
        "drawing_file": summary["drawing_file"],
    }