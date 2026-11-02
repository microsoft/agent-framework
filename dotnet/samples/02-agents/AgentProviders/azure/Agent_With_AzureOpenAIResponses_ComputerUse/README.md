# Computer use with Microsoft Foundry Responses

This sample shows how to use the generally available (GA) computer tool with an `AIAgent` backed by a Microsoft Foundry project Responses endpoint.

## What this sample demonstrates

- Using the parameterless `FoundryAITool.CreateComputerTool()` to add the GA `computer` tool (`{"type":"computer"}`)
- Running every action of a batched `computer_call` (the GA call returns an ordered `actions` list) before sending back one screenshot
- Uploading screenshots to Foundry Files and returning file IDs from the computer loop

For the preview `computer_use_preview` tool with a Microsoft Foundry project, which takes an environment and display size and returns a single `action` per call, see [Agent_Step15_ComputerUsePreview](../../foundry/Agent_Step15_ComputerUsePreview/).

| | GA tool (this sample) | Preview tool (Agent_Step15_ComputerUsePreview) |
| --- | --- | --- |
| Factory | `FoundryAITool.CreateComputerTool()` | `FoundryAITool.CreateComputerTool(environment, width, height)` |
| Wire tool | `{"type":"computer"}` | `{"type":"computer_use_preview", ...}` |
| Actions per call | ordered `actions` batch | single `action` |

For more information, see the OpenAI [computer use guide](https://developers.openai.com/api/docs/guides/tools-computer-use).

## Known limitation

The sample continues each turn from the stored response, so only the new `computer_call_output` is sent. Sending a GA `computer_call` back to the model instead (for example with stored responses disabled and the history kept locally) currently fails. The OpenAI .NET SDK models only the preview item and adds `"action": null`, which the Responses API rejects for the GA tool.

## How the simulation works

**This sample does not connect to a real browser.** It intercepts the model's actions and returns pre-captured screenshots as if the actions were performed:

| State | Reached by | Screenshot sent back |
| --- | --- | --- |
| Initial | Session start | `cua_browser_search.jpg`, an empty search page |
| Typed | A `type` action | `cua_search_typed.jpg`, search text in the box |
| Search submitted | A `keypress` of Enter, or a `click` after typing | `cua_search_results.jpg`, the results page |

Each loop iteration runs all actions of the call in order, then sends the screenshot for the resulting state. The loop ends when the model stops returning computer calls after the search was submitted, or after 10 iterations.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project with a deployment of a model that supports the GA computer tool (for example `gpt-5.4`)
- Foundry Files configured for the project, including storage access for the project's managed identity
- An authenticated Azure identity with access to the project (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4" # Optional, defaults to gpt-5.4
```

## Run the sample

```powershell
dotnet run
```