// Copyright (c) Microsoft. All rights reserved.

// Multi-Model Routing — Switch the model an agent talks to, mid-conversation
//
// This sample shows how to use the RoutePersistingRoutingChatClient to route each agent turn to one of
// several named chat clients (routes), where the route that is active for a session is persisted
// in the session's state bag.
//
// Because the conversation history is kept client side by the agent's chat history provider, the
// full history is replayed to whichever model handles the next turn. Switching route therefore
// preserves the conversation — no manual rehydration is required.
//
// The sample runs a simple interactive loop. In addition to chatting with the agent, you can:
//   /route           — show the route that is currently active for the session
//   /route <name>    — switch the session to the named route
//   /exit            — quit (an empty line also exits)

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var primaryModel = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var secondaryModel = Environment.GetEnvironmentVariable("FOUNDRY_MODEL_ALTERNATE") ?? "gpt-5.4";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var responsesClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetProjectResponsesClient();

// <create_routing_client>
// Each route is an ordinary IChatClient. Here both routes target the same project but a different
// model deployment; they could equally be clients for entirely different providers.
// Stored output is disabled so that the conversation is carried client side and can be replayed
// against whichever model handles the next turn.
var routingClient = new RoutePersistingRoutingChatClient(
    new Dictionary<string, IChatClient>
    {
        [primaryModel] = responsesClient.AsIChatClientWithStoredOutputDisabled(primaryModel),
    },
    new RoutePersistingRoutingChatClientOptions { DefaultRoute = primaryModel });

// Routes remain mutable after construction. Add, replace, or remove entries only when no requests are in flight.
routingClient.Routes[secondaryModel] = responsesClient.AsIChatClientWithStoredOutputDisabled(secondaryModel);
// </create_routing_client>

AIAgent agent = routingClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "Router",
    ChatOptions = new() { Instructions = "You are a helpful assistant. Always state which model you are when asked." },

    // Keep the conversation client side so it survives a route change.
    ChatHistoryProvider = new InMemoryChatHistoryProvider(),
});

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine($"Routes: {string.Join(", ", routingClient.Routes.Keys)}");
Console.WriteLine($"Active route: {routingClient.GetActiveRoute(session)}");
Console.WriteLine("Type a message, '/route <name>' to switch model, or '/exit' to quit.");

while (true)
{
    Console.Write("\nYou > ");
    var input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input) || input.Equals("/exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    if (input.StartsWith("/route", StringComparison.OrdinalIgnoreCase))
    {
        HandleRouteCommand(input);
        continue;
    }

    var response = await agent.RunAsync(input, session);
    Console.WriteLine($"\n[{routingClient.GetActiveRoute(session)}] Agent > {response}");
}

// <switch_route>
// Reading and changing the active route for a session. The new route is persisted in the session's
// state bag, so it applies to every subsequent turn of that session.
void HandleRouteCommand(string input)
{
    var requested = input.Length > "/route".Length ? input["/route".Length..].Trim() : string.Empty;

    if (requested.Length == 0)
    {
        Console.WriteLine($"Active route: {routingClient.GetActiveRoute(session)}");
        return;
    }

    if (!routingClient.Routes.ContainsKey(requested))
    {
        Console.WriteLine($"Unknown route '{requested}'. Available: {string.Join(", ", routingClient.Routes.Keys)}");
        return;
    }

    routingClient.SetActiveRoute(session, requested);
    Console.WriteLine($"Switched to route: {requested}");
}
// </switch_route>
