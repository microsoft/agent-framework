# CUA Samples on macOS

Run the CUA getting-started samples on macOS Ventura/Monterey (Apple Silicon or Intel).

## Prerequisites

- macOS 12+ with administrator access
- [Homebrew](https://brew.sh/) (recommended)
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Python 3.13 and [uv](https://docs.astral.sh/uv/)

Install the basics via Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git python@3.13 uv
brew install --cask docker
```

## Setup

```bash
cd ~/workspace
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python

# Create & activate venv
uv venv
source .venv/bin/activate

# Install dependencies (DevUI builds fine on macOS)
uv sync --dev

# Set Anthropic key for this shell
export ANTHROPIC_API_KEY="sk-ant-your-key"
```

Ensure Docker Desktop is running (menu bar whale icon steady), then pull the desktop image:

```bash
docker pull trycua/cua-xfce:latest
```

## Run a Sample

```bash
python samples/getting_started/cua/basic_example/main.py
```

## Common Errors

| Symptom | Fix |
| --- | --- |
| `invalid_request_error: instructions: Extra inputs are not permitted` | Remove `instructions=` from `CuaAgentMiddleware` / `CuaChatClient`; provide guidance via the task prompt. |
| Docker command not found | Start Docker Desktop: `open -a Docker`. Wait until it reports “Docker is running”. |
| `RuntimeError: CuaChatClient._inner_get_response should not be called` | Always instantiate `ChatAgent` with `CuaAgentMiddleware`; do not call the chat client directly. |
| Container reuses old ports | Stop/remove: `docker stop trycua_cua-xfce_latest && docker rm trycua_cua-xfce_latest`. |
| Anthropic auth errors | Confirm `export ANTHROPIC_API_KEY=...` in the active shell (or store in `.env` / shell profile). |
| Want native macOS automation | Install Lume (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/lume/scripts/install.sh)"`) and switch `Computer(os_type="linux", provider_type="docker", ...)` to `Computer(os_type="macos", provider_type="lume")`. |


