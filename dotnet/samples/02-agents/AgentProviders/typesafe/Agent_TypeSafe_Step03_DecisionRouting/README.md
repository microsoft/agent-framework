# Routing an agent's requests with a decision model

This sample routes each request of an agent to a fast model or a reasoning model, and a decision model chooses the
route. It combines `RoutingChatClient` from Microsoft.Extensions.AI with the decision API proposed for
Microsoft.Extensions.AI ([dotnet/extensions#7795](https://github.com/dotnet/extensions/pull/7795) and
[#7796](https://github.com/dotnet/extensions/pull/7796)), which `Microsoft.Agents.AI.Abstractions` carries until it ships.

## How it works

The route is a Choice among the values of an enum, whose descriptions say when to pick each one:

```csharp
internal enum Route
{
    [Description("Short, routine requests where a quick answer is enough.")]
    Fast,

    [Description("Requests that need multi-step analysis, comparisons, or careful planning.")]
    Reasoning,
}

DecisionDefinition<RouteDecision> routing = DecisionDefinition<RouteDecision>.Create(builder => builder.Choice(decision => decision.Route));
```

`RoutingChatClient.Create` calls a selector before every model call. The selector sends the conversation to the
decision client, and returns the chat client of the chosen route:

```csharp
RoutingChatClient router = RoutingChatClient.Create(async (context, cancellationToken) =>
{
    var state = new RoutingState([.. context.Messages.Select(message => new RoutingMessage(message.Role.Value, message.Text))]);
    DecisionResponse<RouteDecision> decision = await jev.GetResponseAsync(state, routing, cancellationToken: cancellationToken);
    return clients[decision.Result.Route];
});

AIAgent agent = router.AsAIAgent(name: "Assistant", instructions: "...");
```

The agent knows nothing about the routing. The decision also returns the whole distribution (`GetDistribution`), so
the application can see how certain the route is, and could, for example, prefer the reasoning model when the choice
is close.

Each chat client is bound to its own deployment. `RoutingChatClient` forwards the caller's `ChatOptions`, so if your
agent sets `ChatOptions.ModelId`, make each routed client ignore or reject a model that is not its own.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project with two deployed chat models: a fast one and a reasoning one
- Azure CLI installed and authenticated (`az login`)
- A TypeSafe API key

Set the environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"              # Optional fast model, defaults to gpt-5.4-mini
$env:FOUNDRY_REASONING_MODEL="your-reasoning-model"  # Optional, defaults to FOUNDRY_MODEL
$env:TYPESAFE_API_KEY="your-typesafe-api-key"
```

## Running the sample

```powershell
dotnet run
```

For each request, the sample prints the route with both probabilities and the model that answered, followed by the
agent's answer. A short factual question goes to the fast model, and a planning question to the reasoning model.
