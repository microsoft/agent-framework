# A decision as an agent tool

This sample gives a Foundry agent a decision as a tool, with the decision API proposed for Microsoft.Extensions.AI
([dotnet/extensions#7795](https://github.com/dotnet/extensions/pull/7795) and
[#7796](https://github.com/dotnet/extensions/pull/7796)), which `Microsoft.Agents.AI.TypeSafe` carries until it ships.
The agent triages support tickets: it calls the tool with the ticket, and replies from the typed result.

## How it works

The application declares the questions once, as a typed result:

```csharp
DecisionDefinition<TicketAnalysis> analysis = DecisionDefinition<TicketAnalysis>.Create(builder =>
{
    builder.Choice(result => result.Department);
    builder.BinaryProbability(result => result.UrgentProbability);
    builder.Score(result => result.Frustration, [new("calm", "..."), new("annoyed", "..."), new("angry", "...")]);
});
```

`Department` is an enum, so its question is a Choice among its values, and the `[Description]` of each value tells the
decision model what belongs to it. The `[Description]` of each `TicketAnalysis` parameter is the instruction of its
question.

`AsAIFunction` turns the definition into the agent's tool:

```csharp
using IDecisionClient jev = new JevDecisionClient(new ApiKeyCredential(typeSafeApiKey));
AIFunction analyzeTicket = analysis.AsAIFunction<SupportTicket>(jev, new AIFunctionFactoryOptions { Name = "analyze_ticket", ... });
```

The tool's only argument is the `SupportTicket`. The questions and the decision client belong to the application, so
the model cannot change what is asked or which labels exist, and the result is a `TicketAnalysis` rather than raw
answers. Jev, the TypeSafe System One model, answers all three questions in one call.

The last part answers the same tool with `KeywordDecisionClient`, a local `IDecisionClient` that matches words. The
agent and the definition do not change, which is how another decision model, such as Azure OpenAI Decisions, would be
used.

Compare with [Agent_Step25_ClassificationWithJev](../../../Agents/Agent_Step25_ClassificationWithJev/), where the
agent's model writes the questions on every call through `JevAIToolBuilder`.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project with a deployed chat model
- Azure CLI installed and authenticated (`az login`)
- A TypeSafe API key

Set the environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"   # Optional, defaults to gpt-5.4-mini
$env:TYPESAFE_API_KEY="your-typesafe-api-key"
```

## Running the sample

```powershell
dotnet run
```

For each ticket, the sample prints the tool result and the agent's one-line reply. The exact probabilities vary between
runs.
