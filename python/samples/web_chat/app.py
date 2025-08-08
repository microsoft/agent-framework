"""
Web Chat Sample for Python Agent Framework Runtime

This sample mirrors the .NET AgentWebChat sample: a minimal web chat UI talking to the agent runtime HTTP API.
It shows:
 1. Listing available agents (discovery) from /agents
 2. Starting / continuing a conversation with an agent
 3. Maintaining per-user (session) conversation ids
 4. Simple frontend (HTMX + minimal JS) with streaming placeholder (future)

Prerequisites:
  pip install fastapi uvicorn jinja2 httpx
  (The runtime already depends on fastapi for http_api; using httpx client internally.)

Run:
  python app.py
Then open: http://localhost:5173

Expected flow:
 - Landing page lists agents discovered from runtime
 - User picks an agent (defaults to 'helpful')
 - User sends messages; responses appear in chat window
 - Conversation id is kept in a cookie so page reload retains history

NOTE: For simplicity this sample spawns the runtime HTTP API (agent_runtime.http_api) in-process
on a different port (8000) so we keep concerns separated like the .NET sample does with an app host.
"""
from __future__ import annotations
import asyncio
import os
import uuid
import httpx
import subprocess
import socket
from pathlib import Path
from typing import Dict, Any, List, AsyncIterator
from fastapi import FastAPI, Request, Depends, Cookie
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

DEFAULT_RUNTIME_PORT = int(os.environ.get("AGENT_RUNTIME_PORT", "8000"))
DEFAULT_APP_PORT = int(os.environ.get("WEB_CHAT_PORT", "5174"))

def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex(("127.0.0.1", port)) != 0

def resolve_runtime_port() -> int:
    # Try requested/default port, then a small range
    candidate = DEFAULT_RUNTIME_PORT
    if _is_port_free(candidate):
        return candidate
    for p in range(candidate + 1, candidate + 11):  # probe next 10 ports
        if _is_port_free(p):
            return p
    # Fallback: let OS choose ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

RUNTIME_PORT = resolve_runtime_port()
RUNTIME_URL = f"http://127.0.0.1:{RUNTIME_PORT}"

def resolve_app_port() -> int:
    candidate = DEFAULT_APP_PORT
    if _is_port_free(candidate):
        return candidate
    for p in range(candidate + 1, candidate + 11):
        if _is_port_free(p):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

APP_PORT = resolve_app_port()

# ----------------------------------------------------------------------------
# Runtime bootstrap (start separate uvicorn like .NET app host)
# ----------------------------------------------------------------------------
_runtime_process = None

def ensure_runtime() -> None:
    global _runtime_process
    if _runtime_process and _runtime_process.poll() is None:
        return
    # Launch the runtime API (if not already started externally)
    # The runtime package (agent_runtime) lives under python/runtime/agent_runtime
    # We need the cwd to be the directory that contains the agent_runtime package so the module import works.
    # Determine runtime root (python/runtime)
    runtime_root = Path(__file__).resolve().parents[2] / "runtime"
    if not (runtime_root / "agent_runtime").is_dir():
        raise RuntimeError(f"agent_runtime package not found at {runtime_root}")
    env = os.environ.copy()
    env["AGENT_RUNTIME_PORT"] = str(RUNTIME_PORT)
    # Ensure runtime_root is on PYTHONPATH so 'agent_runtime' imports resolve in subprocess
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(runtime_root) + (os.pathsep + existing_path if existing_path else "")
    _runtime_process = subprocess.Popen([
        "python", "-m", "uvicorn", "agent_runtime.http_api:app", "--host", "127.0.0.1", "--port", str(RUNTIME_PORT)
    ], cwd=str(runtime_root), env=env)

# ----------------------------------------------------------------------------
# Web application
# ----------------------------------------------------------------------------
app = FastAPI(title="Python Agent Web Chat")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=RUNTIME_URL, timeout=30.0) as client:
        yield client

# ----------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------
async def discover_agents(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    r = await client.get("/agents")
    r.raise_for_status()
    return r.json()

async def send_agent_message(client: httpx.AsyncClient, agent: str, conversation_id: str, user_text: str) -> Dict[str, Any]:
    payload = {
        "agent_name": agent,
        "conversation_id": conversation_id,
        "messages": [{"role": "user", "content": user_text}]
    }
    r = await client.post(f"/agents/{agent}/run", json=payload)
    r.raise_for_status()
    return r.json()

# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.middleware("http")
async def runtime_middleware(request: Request, call_next):
    # Start runtime lazily on first request
    ensure_runtime()
    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, conversation_id: str | None = Cookie(default=None), client: httpx.AsyncClient = Depends(get_http_client)):
    agents = await discover_agents(client)
    # Choose default agent
    default_agent = next((a for a in agents if a["name"] == "helpful"), agents[0] if agents else None)
    if not conversation_id:
        # new conversation id
        conversation_id = str(uuid.uuid4())
    # Basic chat history kept only in-browser (server stateless for this sample)
    response = templates.TemplateResponse(
        "web_chat_template.html",
        {
            "request": request,
            "agents": agents,
            "default_agent": default_agent,
            "conversation_id": conversation_id,
            "runtime_url": RUNTIME_URL,
        },
    )
    response.set_cookie("conversation_id", conversation_id, httponly=True, path="/")
    return response

@app.post("/chat/send", response_class=HTMLResponse)
async def chat_send(request: Request, client: httpx.AsyncClient = Depends(get_http_client), conversation_id: str | None = Cookie(default=None)):
    form = await request.form()
    agent = form.get("agent") or "helpful"
    message = form.get("message") or ""
    if not message.strip():
        return HTMLResponse("<div class='error'>Empty message.</div>")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    # Send to runtime
    try:
        runtime_response = await send_agent_message(client, agent, conversation_id, message)
        assistant_msg = runtime_response.get("messages", [{}])[0].get("content", "(no response)")
    except Exception as e:
        assistant_msg = f"Error contacting runtime: {e}"  # minimal error surfacing
    # Return partial HTML snippet (HTMX swap)
    return templates.TemplateResponse("_messages_fragment.html", {
        "request": request,
        "user_msg": message,
        "assistant_msg": assistant_msg,
    })

@app.get("/health")
async def health():
    return {"status": "ok"}

# ----------------------------------------------------------------------------
# Shutdown
# ----------------------------------------------------------------------------
@app.on_event("shutdown")
def shutdown_event():
    if _runtime_process and _runtime_process.poll() is None:
        _runtime_process.terminate()

# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    ensure_runtime()
    print(f"Python Agent Web Chat running on http://127.0.0.1:{APP_PORT}")
    print(f"Runtime API at http://127.0.0.1:{RUNTIME_PORT} (auto-started)")
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT)
