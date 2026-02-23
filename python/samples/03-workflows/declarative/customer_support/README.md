# Customer Support Workflow Sample

Multi-agent workflow demonstrating automated troubleshooting with escalation paths.

## Overview

Coordinates six specialized agents to handle customer support requests:

1. **SelfServiceAgent** - Initial troubleshooting with user
2. **TicketingAgent** - Creates tickets when escalation needed
3. **TicketRoutingAgent** - Routes to appropriate team
4. **WindowsSupportAgent** - Windows-specific troubleshooting
5. **TicketResolutionAgent** - Resolves tickets
6. **TicketEscalationAgent** - Escalates to human support

## Files

- `workflow.yaml` - Workflow definition with conditional routing
- `main.py` - Agent definitions and workflow execution
- `ticketing_plugin.py` - Mock ticketing system plugin

## Running

```bash
python main.py
```

## Example Input

```
My PC keeps rebooting and I can't use it.
```

## Requirements

- Azure OpenAI endpoint configured
- `az login` for authentication
