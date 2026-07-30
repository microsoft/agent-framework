# Harness Console

A Textual-based terminal UI for running and observing AI agents built with the Agent Framework.

## Quick Start

```python
from console import run_agent_async, build_default_observers

await run_agent_async(
    agent=my_agent,
    session=my_session,
    observers=build_default_observers(),
)
```

See [`harness_research.py`](../harness_research.py) for a complete example.

## Package Structure

```
console/
├── __init__.py              # Public API exports
├── harness_console.py       # run_agent_async() entry point
├── app.py                   # HarnessApp (Textual application)
├── app_state.py             # HarnessAppState, enums, data types
├── agent_runner.py          # HarnessAgentRunner (streaming orchestration)
├── state_driver.py          # IUXStateDriver protocol
├── textual_state_driver.py  # Textual implementation of IUXStateDriver
├── formatters.py            # Tool call formatters
├── observers/               # Lifecycle observers
│   ├── base.py              #   ConsoleObserver abstract base
│   ├── text_output.py       #   Streaming text display
│   ├── tool_call_display.py #   Tool call formatting
│   ├── tool_approval.py     #   User approval for tool calls
│   ├── error_display.py     #   Error messages
│   ├── usage_display.py     #   Token usage tracking
│   └── reasoning_display.py #   Reasoning/thinking blocks
├── components/              # Textual UI widgets
│   ├── scroll_panel.py      #   Conversation history
│   ├── text_input.py        #   User text input
│   ├── list_selection.py    #   Multiple choice selector
│   ├── agent_status.py      #   Spinner + usage display
│   └── agent_mode_help.py   #   Mode indicator + help text
└── commands/                # Slash command handlers
    ├── base.py              #   CommandHandler abstract base
    ├── exit_handler.py      #   /exit
    ├── mode_handler.py      #   /mode [plan|execute]
    ├── todo_handler.py      #   /todos
    └── session_handler.py   #   /session-export, /session-import
```

## Public API

| Export | Description |
|--------|-------------|
| `run_agent_async` | Main entry point — runs the Textual app with an agent |
| `build_default_observers` | Factory for the standard observer set |
| `build_default_command_handlers` | Factory for slash command handlers |
| `ConsoleObserver` | Base class for custom observers |
| `ToolCallFormatter` | Base class for custom tool formatters |
| `CommandHandler` | Base class for custom slash commands |

## Architecture

The console follows a unidirectional data flow:

```
AgentRunner → Observers → StateDriver → AppState → Textual UI
                                ↑
                          User Input (app.py)
```

- **AgentRunner** streams responses from the agent and dispatches events to observers.
- **Observers** process events (text chunks, tool calls, errors) and update the state driver.
- **StateDriver** (`IUXStateDriver`) mutates `HarnessAppState` and notifies the UI.
- **Textual App** reads state and syncs widgets on each notification.

### Key Design Choices

| Concern | Approach |
|---------|----------|
| Rendering | Textual widgets + Rich markup (no manual ANSI) |
| State | Single `HarnessAppState` dataclass, mutated by driver |
| Streaming text | Truncate-and-rewrite on RichLog for flicker-free updates |
| Extensibility | Custom observers, formatters, and commands via base classes |
| Follow-up questions | Observer returns `FollowUpQuestion` → UI shows prompt/choices |

## Dependencies

- `textual` — TUI framework
- `rich` — Text formatting
- `agent-framework` — Core agent framework

