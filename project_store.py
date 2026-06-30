from __future__ import annotations

import json
import os
import sqlite3
import threading
import math
from dataclasses import dataclass, field, asdict

import engine
import engine_panel

OUTPUT_DIR = engine.OUT_DIR
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "projects.db")

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
    return {"ok": False, "error": message}


def _check_changes(product: str, changes: dict) -> str | None:
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


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id      TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            product TEXT NOT NULL,
            params  TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _save(proj: Project) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO projects (id, name, product, params) VALUES (?, ?, ?, ?)",
            (proj.id, proj.name, proj.product, json.dumps(proj.params)),
        )


def _load() -> None:
    with _db() as conn:
        rows = conn.execute("SELECT id, name, product, params FROM projects").fetchall()
    if rows:
        for id_, name, product, params_json in rows:
            _projects[id_] = Project(id_, name, product, json.loads(params_json))
    else:
        for p in _SEED:
            _projects[p.id] = p
            _save(p)


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



def _prepare(project_id: str, expected_product: str, changes: dict) -> dict:
    proj = _projects.get(project_id)
    if proj is None:
        return _err(f"no project '{project_id}'. Known: {list(_projects)}")
    if proj.product != expected_product:
        return _err(f"project '{project_id}' is a {proj.product}, not a "
                    f"{expected_product}; use the {proj.product} tool instead")
    clean = {k: v for k, v in changes.items() if v is not None}
    if not clean:
        return _err("no parameters given to change")
    bad = _check_changes(proj.product, clean)
    if bad:
        return _err(bad)
    clean = {k: float(v) for k, v in clean.items()}
    candidate = dict(proj.params)
    candidate.update(clean)
    try:
        summary = ENGINES[proj.product].generate(candidate, write_summary=False)
    except Exception as e:                       # noqa: surface, don't crash
        return _err(f"could not regenerate drawing: {e}")
    return {
        "ok": True, "project_id": project_id, "product": proj.product,
        "changed": clean, "candidate_params": candidate,
        "summary": summary, "drawing_file": summary["drawing_file"],
    }


def _apply(project_id: str, expected_product: str, changes: dict) -> dict:
    with _lock:
        prepared = _prepare(project_id, expected_product, changes)
        if not prepared.get("ok"):
            return prepared
        proj = _projects[project_id]
        proj.params = prepared["candidate_params"]
        _save(proj)
        return {
            "ok": True, "project": asdict(proj),
            "changed": prepared["changed"], "summary": prepared["summary"],
            "drawing_file": prepared["drawing_file"],
        }


def propose_change(project_id: str, expected_product: str, changes: dict) -> dict:
    with _lock:
        return _prepare(project_id, expected_product, changes)


def commit_change(project_id: str, candidate_params: dict) -> dict:
    with _lock:
        proj = _require(project_id)
        proj.params = candidate_params
        _save(proj)
        return {"ok": True, "project": asdict(proj)}