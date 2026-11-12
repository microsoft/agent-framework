// Copyright (c) Microsoft. All rights reserved.

// This sample routes each request of an agent to a fast model or a reasoning model, and a decision model chooses the
// route. RoutingChatClient from Microsoft.Extensions.AI asks a selector which chat client handles each call, and the
// selector asks Jev, the TypeSafe System One model, a Choice question through the decision API proposed for
// Microsoft.Extensions.AI. The agent itself is an ordinary agent over the router.

#pragma warning disable MEAI001 // RoutingChatClient and the decision API are experimental.

using System.ClientModel;
using System.ComponentModel;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.TypeSafe;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var fastModel = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var reasoningModel = Environment.GetEnvironmentVariable("FOUNDRY_REASONING_MODEL") ?? fastModel;
var typeSafeApiKey = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? throw new InvalidOperationException("TYPESAFE_API_KEY is not set.");

// 1. The route question: a Choice among the values of Route, whose descriptions tell the decision model when to pick
// each one.
DecisionDefinition<RouteDecision> routing = DecisionDefinition<RouteDecision>.Create(builder => builder.Choice(decision => decision.Route));

// 2. One chat client per route. Each one is bound to its own deployment.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var projectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());
using IChatClient fast = projectClient.GetProjectOpenAIClient().GetProjectResponsesClientForModel(fastModel).AsIChatClientWithStoredOutputDisabled(fastModel);
using IChatClient reasoning = projectClient.GetProjectOpenAIClient().GetProjectResponsesClientForModel(reasoningModel).AsIChatClientWithStoredOutputDisabled(reasoningModel);
Dictionary<Route, IChatClient> clients = new() { [Route.Fast] = fast, [Route.Reasoning] = reasoning };

// <router>
// 3. The router. Before each call, the selector sends the conversation to the decision client and forwards the call to
// the chat client of the chosen route. The decision returns the whole distribution, so the route's certainty is
// visible, and the application could, for example, prefer the reasoning model when the choice is close.
using IDecisionClient jev = new JevDecisionClient(new ApiKeyCredential(typeSafeApiKey));
using RoutingChatClient router = RoutingChatClient.Create(async (context, cancellationToken) =>
{
    var state = new RoutingState([.. context.Messages.Select(message => new RoutingMessage(message.Role.Value, message.Text))]);
    DecisionResponse<RouteDecision> decision = await jev.GetResponseAsync(state, routing, cancellationToken: cancellationToken);
    IReadOnlyDictionary<Route, double> distribution = decision.GetDistribution(result => result.Route);

    Route route = decision.Result.Route;
    Console.WriteLine($"Route: {route} (fast {distribution[Route.Fast]:F2}, reasoning {distribution[Route.Reasoning]:F2}), model {(route == Route.Fast ? fastModel : reasoningModel)}");
    return clients[route];
});
// </router>

// 4. The agent. It knows nothing about the routing; every model call goes through the router.
AIAgent agent = router.AsAIAgent(name: "Assistant", instructions: "You are a helpful assistant. Answer in at most three sentences.");

string[] requests =
[
    "What is the capital of France?",
    "We are launching a product with no sales history. Compare three ways to forecast its first-year demand, and recommend one with its main risk.",
];

foreach (string request in requests)
{
    Console.WriteLine($"User: {request}");
    AgentResponse response = await agent.RunAsync(request);
    Console.WriteLine($"Agent: {response.Text}");
    Console.WriteLine();
}

/// <summary>The routes. Each description tells the decision model when to pick the route.</summary>
internal enum Route
{
    [Description("Short, routine requests where a quick answer is enough.")]
    Fast,

    [Description("Requests that need multi-step analysis, comparisons, or careful planning.")]
    Reasoning,
}

#pragma warning disable CA1812 // RouteDecision is created from the answers.

/// <summary>The decision: the route of the latest request.</summary>
internal sealed record RouteDecision([Description("Which model should answer the latest user request?")] Route Route);

#pragma warning restore CA1812

/// <summary>The state the decision model reads: the conversation, as role and text.</summary>
internal sealed record RoutingState(IReadOnlyList<RoutingMessage> Messages);

/// <summary>One message of the conversation.</summary>
internal sealed record RoutingMessage(string Role, string Text);
