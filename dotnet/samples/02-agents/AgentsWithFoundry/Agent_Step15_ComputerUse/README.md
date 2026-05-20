# Computer Use with the Responses API

This sample shows how to use the Computer Use tool with `AIProjectClient.AsAIAgent(...)`.

## What this sample demonstrates

- Using `FoundryAITool.CreateComputerTool()` to add computer use capabilities
- Processing computer call actions (click, type, key press)
- Managing the computer use interaction loop with screenshots

For more information, see [Use the computer tool](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/computer-use?pivots=csharp).

## How the simulation works

In a real computer use scenario, the model controls a virtual keyboard and mouse to interact with a live browser — typing text, clicking buttons, and pressing keys. The host application captures a screenshot after each action and sends it back to the model so it can decide what to do next.

**This sample does not connect to a real browser.** Instead, it intercepts the model's actions and returns pre-captured screenshots as if the actions were actually performed. No real typing, clicking, or key presses happen — the sample fakes the environment so you can explore the computer use protocol without any browser automation setup.

### State transitions

The model receives a screenshot as input, analyzes it, and responds with a computer action as output. The sample maps each action to a new state and returns the corresponding screenshot:

| Step | Model Action    | What Happens                              | Screenshot Sent Back to Model                                |
|------|-----------------|-------------------------------------------|--------------------------------------------------------------|
| 1    |                 | Session starts with the user prompt       | `cua_browser_search.jpg` — empty search page                 |
| 2    | Click           | Model clicks the search box to focus it   | `cua_browser_search.jpg` — same page                         |
| 3    | Type            | Model types the search query into the box | `cua_search_typed.jpg` — search text visible in the box      |
| 3a   | *(text response)* | Model may ask for confirmation instead of acting | `cua_search_typed.jpg` — same page |
| 4    | KeyPress Enter  | Model presses Enter to submit the search  | `cua_search_results.jpg` — search results page               |

### Interaction loop

1. The user prompt and the initial screenshot (`cua_browser_search.jpg` — an empty search page) are sent to the model as input.
2. The model analyzes the screenshot and responds with a computer action (e.g., click on the search box to focus it, then type search text, then press Enter).
3. The sample intercepts the action, advances the state, and sends back the next pre-captured screenshot as if the action was performed on a real browser.
4. Steps 2–3 repeat until the model stops requesting actions or the iteration limit is reached.

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_COMPUTER_USE_DEPLOYMENT_NAME="computer-use-preview"
```

## Run the sample

```powershell
dotnet run
```
