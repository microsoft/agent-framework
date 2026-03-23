# Deep Research Workflow Sample

Multi-agent workflow implementing the "Magentic" orchestration pattern from AutoGen.

## Overview

Coordinates specialized agents for complex research tasks:

**Orchestration Agents:**
- **ResearchAgent** - Analyzes tasks and correlates relevant facts
- **PlannerAgent** - Devises execution plans
- **ManagerAgent** - Evaluates status and delegates tasks
- **SummaryAgent** - Synthesizes final responses

**Capability Agents:**
- **KnowledgeAgent** - Performs web searches
- **CoderAgent** - Writes and executes code
- **WeatherAgent** - Provides weather information

## Files

- `main.py` - Agent definitions and workflow execution (programmatic workflow)

## Running

```bash
python main.py
```

## Requirements

- Azure OpenAI endpoint configured
- `az login` for authentication
