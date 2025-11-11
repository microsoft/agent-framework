# Cua Integration Samples

Samples demonstrating how to use Cua with Microsoft Agent Framework for desktop automation.

> [!IMPORTANT]
> **Experimental Feature**: This integration is experimental and **not recommended for production use**. These samples are for development, testing, and exploration only.

## Prerequisites

- Install the samples (`uv sync --dev` from the `python/` folder)
- Set required API keys in your shell (at minimum `ANTHROPIC_API_KEY`; `OPENAI_API_KEY` is only needed for `workflow_orchestration`)
- Pull the desktop image once: `docker pull trycua/cua-xfce:latest`

## Samples

### 1. [Basic Example](./basic_example/)

Basic usage with Anthropic Claude on Linux Docker.

**Shows:**
- Setting up Cua computer with Docker provider
- Creating `CuaAgentMiddleware`
- Running basic desktop automation tasks

```bash
cd basic_example
python main.py
```

### 2. [Composite Agent](./composite_agent/)

Advanced example using composite agents (grounding + planning models).

**Shows:**
- Combining UI-Tars (grounding) with GPT-4o (planning)
- Automatic model coordination
- Platform-specific setup (macOS Lume)

```bash
cd composite_agent
python main.py
```

### 3. [Workflow Orchestration](./workflow_orchestration/)

Multi-agent workflow showing Agent Framework orchestration with Cua.

**Shows:**
- Research agent (pure Agent Framework)
- Cua agent for automation
- Verification agent (pure Agent Framework)
- Agent Framework workflow patterns
- Thread management and context passing

```bash
cd workflow_orchestration
python main.py
```

## Platform Setup

### Linux on Docker (Recommended - Cross-platform)

See the platform-specific quickstarts in `setup/` for full environment instructions:

- [`setup/windows.md`](./setup/windows.md)
- [`setup/macos.md`](./setup/macos.md)
- [`setup/linux.md`](./setup/linux.md)

## Resources

- [Cua Documentation](https://docs.cua.ai)
  - [Computers](https://docs.cua.ai/docs/computer-sdk/computers)
  - [Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops)
- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
- [Package README](../../../packages/cua/README.md)
