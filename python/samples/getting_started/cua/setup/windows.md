# CUA Samples on Windows

This quickstart runs the CUA getting-started samples on native Windows 10/11 using PowerShell.

## Prerequisites

- Windows 10/11 with administrator access
- [Docker Desktop](https://www.docker.com/products/docker-desktop) (Linux container mode)
- [Python 3.13](https://www.python.org/downloads/) and `pip`
- [uv](https://docs.astral.sh/uv/) (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`)
- Optional: Visual C++ Build Tools if you plan to install DevUI extras

## Setup

```powershell
# Clone the repo
cd C:\src
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework\python

# Create and activate a Python 3.13 virtual environment
uv python install 3.13
uv venv --python 3.13
.venv\Scripts\Activate.ps1

# Install dependencies (skip DevUI which requires build tools)
uv sync --dev --no-install-package agent-framework-devui

# Set Anthropic key for this session
$env:ANTHROPIC_API_KEY = "sk-ant-your-key"
```

Pull the desktop image once:

```powershell
docker pull trycua/cua-xfce:latest
```

## Run a Sample

```powershell
python samples\getting_started\cua\basic_example\main.py
```

## Common Errors

| Symptom | How to fix |
| --- | --- |
| `invalid_request_error: instructions: Extra inputs are not permitted` | Remove any `instructions=` arguments from `CuaAgentMiddleware` or `CuaChatClient`. Supply guidance in the user prompt instead. |
| Sample hangs after “Starting VM …” | Docker Desktop is still starting or a stale container exists. Restart Docker or run `docker stop trycua_cua-xfce_latest` followed by `docker rm trycua_cua-xfce_latest`. |
| `Bind for 0.0.0.0:8006 failed: port is already allocated` | Another process/container uses the port. Stop the old container or override ports via `Computer(..., api_port=, vnc_port=)`. |
| `RuntimeError: CuaChatClient._inner_get_response should not be called` | Always create a `ChatAgent` with `CuaAgentMiddleware`; never call the chat client directly. |
| `ANTHROPIC_API_KEY present? False` | The key isn’t set in the active shell. Run `$env:ANTHROPIC_API_KEY = "sk-..."` after activating the venv or persist it via `setx`. |
| `docker: no matching manifest for linux/amd64` | You pulled `trycua/cua-ubuntu:latest`. Use `trycua/cua-xfce:latest` for amd64 hosts. |


