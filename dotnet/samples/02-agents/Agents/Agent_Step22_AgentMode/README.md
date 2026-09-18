# Agent Mode

This sample demonstrates how to use the `AgentModeProvider` to track and switch an agent's
operating **mode** at runtime, and drive different agent behavior depending on the active mode.

The `AgentModeProvider` is an `AIContextProvider` that stores the current mode in the session
state and injects it into the instructions sent to the model on every turn. It also exposes
`mode_get` and `mode_set` tools so the agent can query and switch modes on its own as its work
progresses.

## What it demonstrates

- Attaching an `AgentModeProvider` to an agent via `ChatClientAgentOptions.AIContextProviders`.
- The provider's **built-in** modes: `plan` (interactive planning) and `execute` (autonomous execution).
- **Customizing** the available modes with `AgentModeProviderOptions` (set the
  `AGENT_MODE_USE_CUSTOM` environment variable to `true` to switch to a simple `concise` /
  `detailed` mode set).
- Reading and changing the mode from application code with `GetModeAsync` / `SetModeAsync`.
- A simple interactive input loop that lets the user switch mode with a slash command. When the
  mode changes this way, the provider injects a notification on the next turn so the agent adjusts
  its behavior.

## Commands

| Command | Description |
|---|---|
| `/mode` | Show the current mode |
| `/mode <name>` | Switch to the named mode |
| `/help` | List the available commands and modes |
| `/exit` | Quit (an empty line also exits) |

Any other input is sent to the agent as a message.

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry project endpoint and model configured
- Azure CLI installed and authenticated (run `az login`)
- User has the required role to invoke models in the Foundry project

## Running the sample

Set the required environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project-endpoint"
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
```

Run the sample:

```powershell
dotnet run
```

To try the custom modes instead of the built-in `plan` / `execute` modes, set the
`AGENT_MODE_USE_CUSTOM` environment variable to `true` and re-run:

```powershell
$env:AGENT_MODE_USE_CUSTOM="true"
dotnet run
```
