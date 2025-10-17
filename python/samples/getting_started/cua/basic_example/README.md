# Basic Cua Example

Basic usage of Cua integration with Microsoft Agent Framework.

## What This Shows

- Setting up Cua computer with Linux Docker provider (cross-platform)
- Creating `CuaAgentMiddleware` with Anthropic Claude
- Human-in-the-loop approval workflows
- Running desktop automation tasks

## Prerequisites

```bash
# Install Docker Desktop or Docker Engine
docker pull --platform=linux/amd64 trycua/cua-xfce:latest

# Set API key
export ANTHROPIC_API_KEY="your-key"
```

## Running

```bash
python main.py
```

## How It Works

1. **Computer Setup**: Initializes Linux Docker container
2. **Middleware**: `CuaAgentMiddleware` wraps Cua's `ComputerAgent`
3. **Agent**: Agent Framework provides orchestration and approval workflows
4. **Execution**: Cua handles model inference, computer control, multi-step loops

## Platform Options

This example uses Linux Docker (recommended). You can also use:

**macOS VM:**
```python
Computer(os_type="macos", provider_type="lume")
```

**Windows Sandbox:**
```python
Computer(os_type="windows", provider_type="winsandbox")
```

See [parent README](../README.md) for setup instructions.

## Resources

- [Cua Computers](https://docs.cua.ai/docs/computer-sdk/computers) - Platform setup guides (Docker, macOS, Windows)
- [Cua Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops) - How Cua's ComputerAgent works
