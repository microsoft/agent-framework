# CUA Samples on Linux (WSL or Native)

Run the CUA getting-started samples on Ubuntu—either native or inside WSL2.

## Prerequisites

- Ubuntu 22.04+ (native) or Windows 10/11 with WSL2 (Ubuntu distro)
- Docker Engine or Docker Desktop (with WSL integration enabled)
- Python 3.13
- [uv](https://docs.astral.sh/uv/)

For WSL users, enable integration in Docker Desktop → Settings → Resources → WSL Integration.

## Setup

```bash
cd ~/workspace
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc    # or ~/.zshrc

# Create & activate venv
uv venv
source .venv/bin/activate

# Install dependencies
uv sync --dev

# Set Anthropic key for this shell
export ANTHROPIC_API_KEY="sk-ant-your-key"
```

Pull the desktop image:

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
| `Cannot connect to the Docker daemon` | Ensure Docker service is running. On WSL, verify integration is enabled; on native Linux, start Docker (`sudo systemctl start docker`). |
| `permission denied while trying to connect to Docker` | Add your user to the docker group: `sudo usermod -aG docker $USER` then reboot or `wsl --shutdown`. |
| `invalid_request_error: instructions: Extra inputs are not permitted` | Remove `instructions=` from `CuaAgentMiddleware` / `CuaChatClient`; keep guidance in the task prompt. |
| Stuck at “Waiting for VM …” | Remove stale containers: `docker stop trycua_cua-xfce_latest && docker rm trycua_cua-xfce_latest`. |
| Anthropic key missing | Verify `echo $ANTHROPIC_API_KEY` after activating the venv. |
| Slow file access on WSL | Work inside the Linux filesystem (`~/workspace`), not `/mnt/c`. |


