# Python Agent Web Chat Sample

This sample mirrors the .NET `AgentWebChat` by providing a minimal web chat UI that communicates with the Python Agent Runtime's HTTP API.

## Features
- Auto-discovers agents from `GET /agents`
- Sends chat messages to selected agent via `POST /agents/{agent}/run`
- Maintains a conversation id in a cookie (server stateless for history)
- Simple HTML UI using HTMX for partial updates (no heavy SPA framework)
- Automatically boots the runtime API (port 8000) alongside the web UI (port 5173)

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

## Alignment with .NET Sample
The .NET version uses Aspire service defaults and separate projects for app host & web. This Python version keeps a similar separation logically by spawning the runtime as a sibling process while the web layer focuses only on UI + HTTP calls.

---
> This is an educational sample and not production-hardened. For production, supervise subprocess lifecycle, add error handling, logging, observability, and security controls.
