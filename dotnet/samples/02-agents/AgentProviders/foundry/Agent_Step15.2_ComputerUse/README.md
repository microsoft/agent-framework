# Computer use with the GA computer tool

This sample shows how to use the generally available (GA) computer tool with an `AIAgent`.

## What this sample demonstrates

- Using the parameterless `FoundryAITool.CreateComputerTool()` to add the GA `computer` tool (`{"type":"computer"}`)
- Running every action of a batched `computer_call` (the GA call returns an ordered `actions` list) before sending back one screenshot
- Returning screenshots as inline image data, so no file upload or cleanup is needed

For the preview `computer_use_preview` tool, which takes an environment and display size and returns a single `action` per call, see [Agent_Step15_ComputerUsePreview](../Agent_Step15_ComputerUsePreview/).

| | GA tool (this sample) | Preview tool (Step15) |
| --- | --- | --- |
| Factory | `FoundryAITool.CreateComputerTool()` | `FoundryAITool.CreateComputerTool(environment, width, height)` |
| Wire tool | `{"type":"computer"}` | `{"type":"computer_use_preview", ...}` |
| Actions per call | ordered `actions` batch | single `action` |

For more information, see the OpenAI [computer use guide](https://developers.openai.com/api/docs/guides/tools-computer-use).

## Microsoft Foundry support

Microsoft Foundry does not accept the GA `computer` tool type yet. Until it does, the sample runs against the public OpenAI Responses API. The Foundry setup is already in `Program.cs`, commented out: once Foundry supports the GA tool, uncomment it (and the `Azure.*` usings at the top), remove the OpenAI setup, and set the Foundry environment variables below.

## Known limitation

The sample continues each turn from the stored response, so only the new `computer_call_output` is sent. Sending a GA `computer_call` back to the model instead (for example with stored responses disabled and the history kept locally) currently fails. The OpenAI .NET SDK models only the preview item and adds `"action": null`, which the Responses API rejects for the GA tool.

## How the simulation works

**This sample does not connect to a real browser.** It intercepts the model's actions and returns pre-captured screenshots (shared with the Step15 sample) as if the actions were performed:

| State | Reached by | Screenshot sent back |
| --- | --- | --- |
| Initial | Session start | `cua_browser_search.jpg`, an empty search page |
| Typed | A `type` action | `cua_search_typed.jpg`, search text in the box |
| Search submitted | A `keypress` of Enter, or a `click` after typing | `cua_search_results.jpg`, the results page |

Each loop iteration runs all actions of the call in order, then sends the screenshot for the resulting state. The loop ends when the model stops returning computer calls after the search was submitted, or after 10 iterations.

## Prerequisites

- .NET 10 SDK or later
- An OpenAI API key with access to a model that supports the GA computer tool (for example `gpt-5.4`)

Set the following environment variables:

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_CHAT_MODEL_NAME="gpt-5.4" # Optional, defaults to gpt-5.4
```

When switching to Microsoft Foundry, set these instead:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_COMPUTER_USE_DEPLOYMENT_NAME="gpt-5.4"
```

## Run the sample

```powershell
dotnet run
```
