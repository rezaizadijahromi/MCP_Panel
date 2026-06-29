"""MCP server — exposes the design engines as tools (stdio transport)."""
from fastmcp import FastMCP

import project_store as store

mcp = FastMCP("acoustics_cad")   


@mcp.tool
def list_projects() -> list[dict]:
    """List every design project with its product type ('silencer' or 'panel')
    and current parameters. ALWAYS call this first to resolve a project's
    human name (e.g. 'the studio panel') to its id before changing it."""
    return store.list_projects()


@mcp.tool
def get_project(project_id: str) -> dict:
    """Get one project's product type and current parameters by id."""
    return store.get_project(project_id)


@mcp.tool
def update_silencer_design(
    project_id: str,
    length_mm: float | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
) -> dict:
    """Change a SPLITTER SILENCER project's geometry and regenerate its drawing.
    Use ONLY for projects whose product is 'silencer'. Pass only the dimensions
    you want to change; omit the rest. Returns the updated figures (peak TL,
    open-area ratio, ...) and the regenerated drawing file."""
    return store.update_silencer(project_id, length_mm, width_mm, height_mm)


@mcp.tool
def update_panel_design(
    project_id: str,
    panel_width_mm: float | None = None,
    panel_height_mm: float | None = None,
    rockwool_mm: float | None = None,
    epdm_mm: float | None = None,
    steel_mm: float | None = None,
) -> dict:
    """Change an ACOUSTIC PANEL project's layer build-up and regenerate its
    drawing. Use ONLY for projects whose product is 'panel'. The acoustically
    meaningful params are the layer thicknesses (rockwool / epdm / steel);
    width and height are cosmetic. Returns the updated figures (NRC, peak
    absorption, ...) and the regenerated drawing file."""
    return store.update_panel(project_id, panel_width_mm, panel_height_mm,
                              rockwool_mm, epdm_mm, steel_mm)


if __name__ == "__main__":
    mcp.run()   # stdio