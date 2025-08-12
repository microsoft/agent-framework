# Python Agent Web Chat Sample

This sample mirrors the .NET `AgentWebChat` by providing a minimal web chat UI that uses the **AgentProxy pattern** to communicate with agents running in the Python Agent Runtime.

## Key Features
- **AgentProxy Pattern**: Uses `AgentProxy` and `HttpActorClient` to treat remote agents as local AIAgent instances
- **HTTP Actor Communication**: Demonstrates the same architecture as .NET's HttpActorClient
- **Agent Discovery**: Auto-discovers agents from `GET /agents` endpoint
- **Thread Management**: Uses `AgentProxyThread` for conversation continuity
- **Clean Architecture**: Web App → AgentProxy → HttpActorClient → Agent Runtime HTTP API
- Simple HTML UI using HTMX for partial updates (no heavy SPA framework)
- Automatically boots the runtime API (port 8000) alongside the web UI (port 5174)

## Structure
```
web_chat/
  app.py                  # FastAPI web app (UI) + runtime process bootstrap
  web_chat_template.html  # Main page template
  _messages_fragment.html # Partial snippet returned on message send
  static/style.css        # Minimal styling
```

## Prerequisites
Install dependencies (in addition to repository base requirements):
```
pip install fastapi uvicorn jinja2 httpx
```

## Run
```
python app.py
```
Then open http://127.0.0.1:5173

You should see the agents, be able to send messages, and receive responses from the runtime.

## Expected Output (Console)
```
Python Agent Web Chat running on http://127.0.0.1:5173
Runtime API at http://127.0.0.1:8000 (auto-started)
```

## Next Enhancements (Ideas)
- Persist and render full conversation history (pull from runtime state)
- Add SSE streaming for incremental token updates
- Multi-agent selection dropdown + switch mid-conversation
- Add markdown rendering for assistant messages
- Authentication & rate limiting example
- Frontend build tooling (optional)

## Architecture Comparison

### .NET AgentWebChat Architecture:
```
Web App → AgentProxy → HttpActorClient → Agent Host → Runtime → AgentActor → AIAgent
```

### Python AgentWebChat Architecture (Updated):
```
Web App → AgentProxy → HttpActorClient → Runtime HTTP API → Runtime → AgentActor → AIAgent  
```

## Key Components

- **`AgentProxy`**: Python equivalent of .NET AgentProxy - makes remote agents feel like local AIAgent instances
- **`HttpActorClient`**: Python equivalent of .NET HttpActorClient - handles HTTP communication with the actor runtime
- **`AgentProxyThread`**: Python equivalent of .NET AgentProxyThread - manages conversation threads

## Code Example
```python
# Create proxy to remote agent (just like .NET)
actor_client = HttpActorClient("http://localhost:8000")  
agent_proxy = AgentProxy("helpful", actor_client)

# Use like any local AIAgent
thread = AgentProxyThread("conversation_123")
response = await agent_proxy.run("Hello!", thread=thread)
```

## Alignment with .NET Sample
This Python version now matches the .NET architecture by using the same AgentProxy pattern. The .NET version uses Aspire service defaults and separate projects, while this Python version spawns the runtime as a subprocess for simplicity, but the core proxy communication pattern is identical.

---
> This is an educational sample and not production-hardened. For production, supervise subprocess lifecycle, add error handling, logging, observability, and security controls.
