import project_store as store

CONFIDENCE_THRESHOLD = 0.5

_PARAM_ALIASES = {
    "silencer": {"length": "length_mm", "width": "width_mm", "height": "height_mm"},
    "panel": {"rockwool": "rockwool_mm", "epdm": "epdm_mm", "steel": "steel_mm",
              "width": "panel_width_mm", "height": "panel_height_mm"},
}


def _resolve_project(projects, name):
    name_l = (name or "").strip().lower()
    if not name_l:
        return None, "no project name found in the email"
    exact = [p for p in projects if p["name"].lower() == name_l]
    partial = [p for p in projects if name_l in p["name"].lower()]
    hits = exact or partial
    if len(hits) == 1:
        return hits[0], None
    known = ", ".join(p["name"] for p in projects)
    if not hits:
        return None, f"no project matches '{name}'. Known projects: {known}"
    return None, f"'{name}' is ambiguous; it matches: " + ", ".join(p["name"] for p in hits)


def _map_changes(product, changes):
    aliases = _PARAM_ALIASES[product]
    mapped, unknown = {}, []
    for ch in changes:
        key = aliases.get(str(ch.get("parameter", "")).strip().lower())
        if key:
            mapped[key] = ch.get("value")
        else:
            unknown.append(ch.get("parameter"))
    return mapped, unknown


def propose_from_extraction(extracted: dict) -> dict:
    if extracted.get("confidence", 0) < CONFIDENCE_THRESHOLD:
        return {"actionable": False,
                "reason": f"low confidence ({extracted.get('confidence', 0):.2f}) "
                          "that this email requests a design change"}
    if not extracted.get("changes"):
        return {"actionable": False, "reason": "no concrete parameter change found"}

    projects = store.list_projects()
    proj, err = _resolve_project(projects, extracted.get("project_name", ""))
    if err:
        return {"actionable": False, "reason": err}

    mapped, unknown = _map_changes(proj["product"], extracted["changes"])
    if not mapped:
        return {"actionable": False,
                "reason": f"none of the requested parameters apply to a "
                          f"{proj['product']}: {unknown}"}

    result = store.propose_change(proj["id"], proj["product"], mapped)
    if not result.get("ok"):
        return {"actionable": False, "reason": result["error"]}

    s = result["summary"]
    return {
        "actionable": True,
        "project_id": proj["id"], "project_name": proj["name"],
        "product": proj["product"], "changed": result["changed"],
        "candidate_params": result["candidate_params"],   # stashed for step 4
        "drawing_file": result["drawing_file"],
        "unknown_parameters": unknown,
        "key_figures": {k: s[k] for k in
                        ("peak_TL_dB", "peak_freq_hz", "NRC", "alpha_peak") if k in s},
    }