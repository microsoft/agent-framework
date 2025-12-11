# Workflow Orchestration Example

Multi-agent workflow demonstrating **Agent Framework + Cua synergies**.

## What This Shows

**Agent Framework Strengths:**
- Workflow orchestration across multiple agents
- Thread and context management
- Human-in-the-loop approval workflows
- Multi-turn conversations

**Cua Strengths:**
- Desktop automation execution
- 100+ model support
- Computer control loops

## The Workflow

```
┌─────────────────────┐
│ 1. Research Agent   │  → Pure Agent Framework (GPT-4o-mini)
│    Create plan      │     Creates automation strategy
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ 2. Automation Agent │  → Agent Framework orchestration
│    Execute plan     │     + Cua execution (Claude Sonnet 4.5)
└──────────┬──────────┘     Agent Framework: approval workflows
           ↓                  Cua: computer control loops
┌─────────────────────┐
│ 3. Verification     │  → Pure Agent Framework (GPT-4o)
│    Confirm results  │     Validates and summarizes
└─────────────────────┘
```

## Prerequisites

```bash
# Install Docker
docker pull --platform=linux/amd64 trycua/cua-xfce:latest

# Set API keys
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
```

## Running

```bash
python main.py
```

## Key Synergies

### 1. **Orchestration**
Agent Framework coordinates the multi-agent workflow while Cua handles automation execution.

### 2. **Thread Management**
```python
thread = automation_agent.get_new_thread()
response = await automation_agent.run(prompt, thread)
```
Agent Framework manages conversation history and context.

### 3. **Human-in-the-Loop**
```python
CuaAgentMiddleware(
    require_approval=True,  # Agent Framework approval workflows
    approval_interval=3,
)
```
Agent Framework's `FunctionApprovalRequestContent` integrates with Cua's execution.

### 4. **Multi-Agent Patterns**
- Research agents (planning)
- Cua agents (execution)
- Verification agents (validation)

Each agent uses the best tool for its role.

## Extending This Pattern

This pattern works for many workflows:

- **Data collection**: Research → Scrape (Cua) → Analyze
- **Testing**: Generate tests → Execute (Cua) → Report
- **Content creation**: Plan → Screenshot (Cua) → Synthesize

Agent Framework provides the orchestration layer, Cua provides the automation layer.

## Resources

- [Cua Agent Loops](https://docs.cua.ai/docs/agent-sdk/agent-loops) - Understanding the agent execution loop
- [Cua Computers](https://docs.cua.ai/docs/computer-sdk/computers) - Platform setup guides
