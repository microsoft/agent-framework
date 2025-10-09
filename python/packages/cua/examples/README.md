# Cua Integration Examples

Examples demonstrating how to use Cua with Agent Framework.

## Prerequisites

```bash
# Install cua packages
pip install cua-agent[all] cua-computer

# Install agent-framework-cua
pip install agent-framework-cua[all]
```

## Examples

### 1. Basic Example (`basic_example.py`)

Shows basic usage with Anthropic Claude on a local macOS VM:

```bash
python examples/basic_example.py
```

Features:
- Human-in-the-loop approval
- Anthropic Claude model
- macOS Lume VM provider

### 2. Composite Agent Example (`composite_agent_example.py`)

Demonstrates composite agents combining grounding + planning models:

```bash
python examples/composite_agent_example.py
```

Features:
- UI-Tars for UI grounding
- GPT-4o for high-level planning
- Automatic coordination between models

## Model Options

### Cloud Models
```python
model="anthropic/claude-3-5-sonnet-20241022"
model="openai/gpt-4o"
model="openai/gpt-4o-mini"
```

### Local Models
```python
model="huggingface-local/ByteDance/OpenCUA-7B"
model="huggingface-local/OpenGVLab/InternVL2-8B"
model="huggingface-local/THUDM/glm-4v-9b"
```

### Composite Models
```python
model="huggingface-local/UI-TARS+openai/gpt-4o"
model="huggingface-local/InternVL+anthropic/claude-3-5-sonnet"
```

## VM Provider Options

### macOS (Lume)
```python
Computer(os_type="macos", provider_type="lume")
```

### Windows Sandbox
```python
Computer(os_type="windows", provider_type="winsandbox")
```

### Docker (Linux)
```python
Computer(os_type="linux", provider_type="docker")
```

### Cloud Sandbox
```python
Computer(
    os_type="linux",
    provider_type="cloud",
    name="your-sandbox",
    api_key="your-api-key",
)
```

## Configuration Options

```python
CuaAgentMiddleware(
    computer=computer,
    model="anthropic/claude-3-5-sonnet-20241022",
    max_trajectory_budget=5.0,      # Max cost budget
    require_approval=True,            # Require human approval
    approval_interval=5,              # Steps between approvals
)
```

## More Information

- [Cua Documentation](https://docs.trycua.com)
- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
