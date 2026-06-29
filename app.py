"""
FastAPI backend — Gemini agent loop over MCP tools.

Routes:
    GET  /api/health  -> {ok, model}
    POST /api/chat    -> {messages:[...]} => {reply, drawing_url}

Run:
    uvicorn app:app --reload
"""
import json
import os

from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from fastmcp import Client          # MCP client (spawns the server over stdio)
from google import genai
from google.genai import types

import project_store as store       # only for OUTPUT_DIR; never mutated here

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_TOOL_STEPS = 6                  # stop runaway tool loops

SYSTEM = (
    "You are a CAD design copilot for acoustic products (splitter silencers and "
    "stratified acoustic panels). The user refers to projects by name; resolve "
    "the name to an id with list_projects BEFORE changing anything. Use the "
    "silencer tool for silencer projects and the panel tool for panel projects. "
    "After a change, briefly state the new key figures (e.g. peak TL, or NRC). "
    "If a requested parameter doesn't apply to that product, say so plainly."
)


def _read_config(path=os.path.join(HERE, "config.txt")) -> dict:
    cfg = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


CFG = _read_config()
API_KEY = CFG.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
MODEL = CFG.get("GEMINI_MODEL", "gemini-2.5-flash")

MCP: Client | None = None
GEMINI: genai.Client | None = None
GEMINI_TOOLS: list[types.Tool] = []


# Gemini rejects some JSON-Schema keys FastMCP emits; collapse anyOf:[T,null]->T.
_DROP = {"title", "additionalProperties", "$schema", "default", "$defs"}


def _clean_schema(s):
    if not isinstance(s, dict):
        return s
    s = {k: v for k, v in s.items() if k not in _DROP}
    if "anyOf" in s:
        non_null = [a for a in s["anyOf"] if a.get("type") != "null"]
        if len(non_null) == 1:
            merged = _clean_schema(non_null[0])
            s.pop("anyOf")
            s.update(merged)
        else:
            s["anyOf"] = [_clean_schema(a) for a in non_null]
    if "properties" in s:
        s["properties"] = {k: _clean_schema(v) for k, v in s["properties"].items()}
    if "items" in s:
        s["items"] = _clean_schema(s["items"])
    return s


def _to_gemini_tools(mcp_tools) -> list[types.Tool]:
    decls = []
    for t in mcp_tools:
        decls.append(types.FunctionDeclaration(
            name=t.name,
            description=t.description or "",
            parameters=_clean_schema(t.inputSchema or {"type": "object", "properties": {}}),
        ))
    return [types.Tool(function_declarations=decls)]


def _to_contents(messages) -> list[types.Content]:
    out = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        out.append(types.Content(role=role,
                                 parts=[types.Part.from_text(text=m.get("content", ""))]))
    return out


def _tool_payload(result) -> dict:
    """Pull a JSON dict out of an MCP CallToolResult across SDK versions."""
    data = getattr(result, "data", None)            # newer FastMCP: deserialized
    if isinstance(data, dict):
        return data
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return {"text": text}
    return {"text": str(result)}


async def run_agent(messages) -> tuple[str, str | None]:
    contents = _to_contents(messages)
    drawing_file = None

    for _ in range(MAX_TOOL_STEPS):
        resp = await GEMINI.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=GEMINI_TOOLS,
                system_instruction=SYSTEM,
            ),
        )
        calls = resp.function_calls or []
        if not calls:
            return (resp.text or "").strip() or "(no reply)", drawing_file

        contents.append(resp.candidates[0].content)
        parts = []
        for call in calls:
            result = await MCP.call_tool(call.name, dict(call.args or {}))
            data = _tool_payload(result)
            if isinstance(data, dict) and data.get("drawing_file"):
                drawing_file = data["drawing_file"]   # newest drawing wins
            parts.append(types.Part.from_function_response(
                name=call.name, response={"result": data}))
        contents.append(types.Content(role="user", parts=parts))

    return "Stopped after too many tool calls — please rephrase.", drawing_file


@asynccontextmanager
async def lifespan(app: FastAPI):
    global MCP, GEMINI, GEMINI_TOOLS
    GEMINI = genai.Client(api_key=API_KEY) if API_KEY else None

    client = Client("mcp_server.py")   # FastMCP infers stdio from the .py path
    await client.__aenter__()          # keep the session open for all requests
    MCP = client
    GEMINI_TOOLS = _to_gemini_tools(await client.list_tools())
    print("Tools:                         ",GEMINI_TOOLS)
    try:
        yield
    finally:
        await client.__aexit__(None, None, None)


app = FastAPI(lifespan=lifespan)
app.mount("/output", StaticFiles(directory=store.OUTPUT_DIR), name="output")


@app.get("/api/health")
def health():
    return {"ok": bool(API_KEY), "model": MODEL if API_KEY else "no API key"}


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    messages = body.get("messages", [])

    if GEMINI is None:
        return JSONResponse({"reply": "No GEMINI_API_KEY set in config.txt.",
                             "drawing_url": None})
    try:
        reply, drawing_file = await run_agent(messages)
    except Exception as e:                          # noqa: surface errors to the GUI
        return JSONResponse({"reply": f"Error: {e}", "drawing_url": None})
    drawing_url = f"/output/{drawing_file}" if drawing_file else None
    return JSONResponse({"reply": reply, "drawing_url": drawing_url})


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))