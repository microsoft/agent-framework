# Composite Agent Example

Demonstrates Cua's composite agent feature, combining multiple models for better performance.

## What This Shows

- **Composite agents**: UI-Tars (grounding) + GPT-4o (planning)
- **Automatic coordination**: Cua handles model routing
- **Cross-platform**: Works with Docker (Linux), macOS, or Windows

## Prerequisites

### Option 1: Docker (Recommended - cross-platform)

```bash
# Install Docker Desktop or Docker Engine
docker pull --platform=linux/amd64 trycua/cua-xfce:latest

# Set API keys
export OPENAI_API_KEY="your-key"  # For GPT-4o
```

### Option 2: macOS (macOS hosts only)

```bash
# Install Lume CLI
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/lume/scripts/install.sh)"

# Start macOS VM
lume run macos-sequoia-cua:latest

# Set API keys
export OPENAI_API_KEY="your-key"  # For GPT-4o
```

## Running

```bash
python main.py
```

## How Composite Agents Work

The model string `"ui-tars+gpt-4o"` tells Cua to use:
- **UI-Tars**: Specialized model for UI element detection and grounding
- **GPT-4o**: Advanced planning and reasoning

Cua automatically coordinates between the models, using each for its strengths.

## Other Composite Combinations

```python
# InternVL for vision + Claude for planning
model="huggingface-local/InternVL+anthropic/claude-3-5-sonnet"

# OpenCUA for grounding + GPT-4o-mini for cost-effective planning
model="huggingface-local/OpenCUA+openai/gpt-4o-mini"
```

## Resources

- [Cua Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops) - Detailed guide on composite agents
- [Cua Computers](https://docs.cua.ai/docs/computer-sdk/computers) - Platform setup guides
