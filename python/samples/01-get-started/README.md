# Get Started with Agent Framework

Progressive samples that build up from a simple agent to a hosted application.

| # | Sample | What You'll Learn | Go Deeper |
|---|--------|-------------------|-----------|
| 1 | [Hello Agent](./01_hello_agent.py) | Create and run a minimal agent | [Agents Overview](../02-agents/) |
| 2 | [Add Tools](./02_add_tools.py) | Give your agent function tools | [Tools Deep Dive](../02-agents/tools/) |
| 3 | [Multi-Turn](./03_multi_turn.py) | Maintain conversation context | [Conversations](../02-agents/conversations/) |
| 4 | [Memory](./04_memory.py) | Add persistent memory/context | [Conversations](../02-agents/conversations/) |
| 5 | [First Workflow](./05_first_workflow.py) | Chain steps in a workflow | [Workflows](../03-workflows/) |
| 6 | [Host Your Agent](./06_host_your_agent.py) | Expose agent via A2A protocol | [Hosting](../04-hosting/) |

## Prerequisites

```bash
pip install agent-framework --pre
```

Set your environment variables:
```bash
export OPENAI_API_KEY="your-key"
# Or for Azure OpenAI:
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
```

## Running

```bash
python 01_hello_agent.py
```
