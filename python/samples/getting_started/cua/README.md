# Cua Integration Samples

Samples demonstrating how to use Cua with Microsoft Agent Framework for desktop automation.

> [!IMPORTANT]
> **Experimental Feature**: This integration is experimental and **not recommended for production use**. These samples are for development, testing, and exploration only.

## Prerequisites

```bash
# Install Cua integration (includes agent-framework-core)
pip install agent-framework-cua

# Set API keys
export ANTHROPIC_API_KEY="your-key"           # For Cua execution (all samples)
export OPENAI_API_KEY="your-key"              # Only for workflow_orchestration sample
```

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

```bash
docker pull --platform=linux/amd64 trycua/cua-xfce:latest
```

### macOS VM (macOS hosts only)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/lume/scripts/install.sh)"
lume run macos-sequoia-cua:latest
```

### Windows Sandbox (Windows hosts only)

```bash
# Enable Windows Sandbox in Windows Features
pip install -U git+git://github.com/karkason/pywinsandbox.git
```

## Resources

- [Cua Documentation](https://docs.cua.ai)
  - [Computers](https://docs.cua.ai/docs/computer-sdk/computers) - Platform setup guides (Docker, macOS, Windows)
  - [Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops) - How Cua's ComputerAgent works
- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
- [Package README](../../../packages/cua/README.md)
