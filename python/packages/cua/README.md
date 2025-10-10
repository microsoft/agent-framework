# Agent Framework - Cua Integration

Computer use integration for Microsoft Agent Framework powered by [Cua](https://github.com/trycua/cua).

## Overview

This package provides seamless integration between Microsoft Agent Framework and Cua, enabling AI agents to control desktop applications across Windows, macOS, and Linux.

### Key Features

- **100+ Model Support**: OpenAI, Anthropic, OpenCUA, InternVL, UI-Tars, GLM, and more
- **Composite Agents**: Combine grounding + planning models (e.g., "ui-tars+gpt-4o")
- **Cross-Platform**: Windows Sandbox, macOS VMs, Linux Docker
- **Human-in-the-Loop**: Built-in approval workflows via Agent Framework middleware
- **Provider Agnostic**: Switch models with a single parameter change

## Installation

```bash
pip install agent-framework-cua

# With all model support
pip install agent-framework-cua[all]
```

## Quick Start

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework_cua import CuaAgentMiddleware
from computer import Computer

async def main():
    # Initialize Cua computer (local macOS VM)
    async with Computer(
        os_type="macos",
        provider_type="lume"
    ) as computer:

        # Create middleware with Anthropic Claude
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            model="anthropic/claude-3-5-sonnet-20241022",
            require_approval=True,
        )

        # Create Agent Framework agent with Cua middleware
        # Note: chat_client is required but won't be used since
        # CuaAgentMiddleware delegates all execution to Cua
        dummy_client = OpenAIChatClient(model_id="gpt-4o-mini")
        agent = ChatAgent(
            chat_client=dummy_client,
            middleware=[cua_middleware],
            instructions="You are a desktop automation assistant.",
        )

        # Run agent
        response = await agent.run(
            "Open Safari and search for 'Python tutorials'"
        )

        print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

## Using Different Models

### OpenAI Computer Use
```python
from agent_framework_cua import CuaAgentMiddleware

cua_middleware = CuaAgentMiddleware(
    computer=computer,
    model="openai/gpt-4o",
)
```

### OpenCUA (Local Model)
```python
from agent_framework_cua import CuaAgentMiddleware

cua_middleware = CuaAgentMiddleware(
    computer=computer,
    model="huggingface-local/ByteDance/OpenCUA-7B",
    require_approval=False,  # No approval for local models
)
```

### Composite Agent (Grounding + Planning)
```python
from agent_framework_cua import CuaAgentMiddleware

# Combine UI-Tars (grounding) with GPT-4o (planning)
cua_middleware = CuaAgentMiddleware(
    computer=computer,
    model="huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B+openai/gpt-4o",
)
```

## Configuration Options

```python
CuaAgentMiddleware(
    computer: Computer,                 # Cua Computer instance
    model: str,                         # Model identifier (100+ supported)
    max_trajectory_budget: float = 5.0, # Max cost budget
    require_approval: bool = True,      # Human approval required
    approval_interval: int = 5,         # Steps between approvals
    stream: bool = True,                # Stream responses
)
```

## Integration with Workflows

```python
from agent_framework.workflows import Workflow, workflow

@workflow
def automation_workflow(task: str) -> str:
    # Step 1: Research with standard agent
    research_agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="Research the task",
    )
    research = research_agent.run(task)

    # Step 2: Automation with Cua
    automation_agent = ChatAgent(
        middleware=[cua_middleware],
        instructions="Execute based on research",
    )
    result = automation_agent.run(research)

    return result
```

## VM Provider Options

### macOS (Lume)
```python
computer = Computer(os_type="macos", provider_type="lume")
```

### Windows Sandbox
```python
computer = Computer(os_type="windows", provider_type="winsandbox")
```

### Docker (Linux)
```python
computer = Computer(os_type="linux", provider_type="docker")
```

### Cloud Sandbox
```python
computer = Computer(
    os_type="linux",
    provider_type="cloud",
    name="your-sandbox-name",
    api_key="your-api-key",
)
```

## Examples

See the [examples](./examples/) directory for more usage patterns:
- Basic computer use
- Multi-model workflows
- Human-in-the-loop approval
- Composite agents
- Integration with Agent Framework workflows

## Resources

- [Cua Documentation](https://docs.trycua.com)
- [Cua GitHub](https://github.com/trycua/cua)
- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)

## License

MIT License - see [LICENSE](./LICENSE) file for details.
