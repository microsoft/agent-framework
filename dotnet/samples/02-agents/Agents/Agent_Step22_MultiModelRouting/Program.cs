// Copyright (c) Microsoft. All rights reserved.

// Multi-model routing with RoutingChatClient
//
// Demonstrates how to back a single agent with multiple chat clients that use
// different models, and switch between them at runtime.
//
// RoutingChatClient is an IChatClient decorator that holds several named inner
// clients and, for each request, routes to one of them based on the active
// destination stored in the session. It also accepts an optional fallback
// factory that builds a client on the fly for any key that is not a registered
// inner client. Here we key the inner clients (and the fallback) by model name.
//
// This sample:
//   1) Registers two inner clients keyed by model name (models A and B).
//   2) Adds a fallback factory that constructs a Foundry client for whatever
//      model name (key) is requested but not pre-registered (model C).
//   3) Retrieves the RoutingChatClient back from the agent via GetService.
//   4) Runs the same agent/session three times, switching the active model
//      between runs with SetActiveDestinationKey, so a single conversation is
//      served by three different models in turn.
//
// Chat history storage
// --------------------
// Every client is created with AsIChatClientWithStoredOutputDisabled(...), i.e.
// the Responses API "store" flag is set to false and chat history is kept
// client-side by the agent's session. This is required when routing across
// clients: service-stored chat history is tied to the *service* that created the
// conversation, so it is only available when every turn is served by that same
// service. Because routing can send different turns to different clients (and
// potentially different services), the conversation must be carried client-side
// so it is replayed to whichever model handles the next turn.
//
// If you instead route only among clients that all share the same service, you
// can use service-stored history (AsIChatClient(...) with storage enabled) and
// let the service persist the conversation.
//
// Reasoning content
// -----------------
// Every client also passes includeReasoningEncryptedContent: false. Encrypted
// reasoning content is model-specific: one model cannot necessarily interpret
// another model's encrypted reasoning, so it must not be echoed back in requests
// when a single conversation is served by multiple models. When you route to only
// a single model, you can leave this enabled (the default) to preserve reasoning
// across turns.

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Two pre-registered models (inner clients) and a third model resolved via the
// fallback factory. Set these to models deployed in your Foundry project.
string modelA = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4";
string modelB = Environment.GetEnvironmentVariable("FOUNDRY_MODEL_ALT1") ?? "gpt-5.4-mini";
string modelC = Environment.GetEnvironmentVariable("FOUNDRY_MODEL_ALT2") ?? "Deepseek-V4-Pro";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());
var responsesClient = aiProjectClient.GetProjectOpenAIClient().GetProjectResponsesClient();

// Register two inner clients keyed by model name. Each uses client-side chat
// history (stored output disabled), and disables encrypted reasoning content
// (includeReasoningEncryptedContent: false) since it is not portable across
// models, so the conversation can move freely between models.
var innerClients = new Dictionary<string, IChatClient>
{
    [modelA] = responsesClient.AsIChatClientWithStoredOutputDisabled(modelA, includeReasoningEncryptedContent: false),
    [modelB] = responsesClient.AsIChatClientWithStoredOutputDisabled(modelB, includeReasoningEncryptedContent: false),
};

// The fallback factory builds a client for any requested model name (key) that
// is not one of the registered inner clients. The created client is used for the
// single request and then disposed by default. You can disable disposal by setting
// the RoutingChatClientOptions.DisableFallbackChatClientDisposal setting to true.
// This allows you to reuse or cache clients created in the fallback factory,
// but you must then manage their disposal yourself.
var routingChatClient = new RoutingChatClient(
    innerClients,
    fallbackFactory: (destinationKey, _, _) =>
    {
        Console.WriteLine($"  (fallback factory building a client for model '{destinationKey}')");
        return new ValueTask<IChatClient>(responsesClient.AsIChatClientWithStoredOutputDisabled(destinationKey, includeReasoningEncryptedContent: false));
    },
    options: new RoutingChatClientOptions
    {
        // If set, can be used to override the active destination in session state for a request.
        // E.g. you could implement a routing heuristic that inspects the request and chooses a model based on its content,
        // or even perform an inference call to a model to decide which model should handle the request.
        Router = null,
    });

AIAgent agent = new ChatClientAgent(
    routingChatClient,
    instructions: "You are a helpful assistant. Keep answers to a single short sentence, and always start by stating which model you are.",
    name: "MultiModelAgent");

AgentSession session = await agent.CreateSessionAsync();

// The RoutingChatClient can be retrieved back from the agent via GetService.
// This is useful when you don't hold a direct reference to it — for example when
// the agent was created elsewhere or resolved from a DI container.
RoutingChatClient routing = agent.GetService<RoutingChatClient>()
    ?? throw new InvalidOperationException("The agent is not backed by a RoutingChatClient.");

// Run 1: default destination — the first registered inner client (model A).
Console.WriteLine($"[Active model: {routing.GetActiveDestinationKey(session) ?? "(default)"}]");
Console.WriteLine(await agent.RunAsync("Give me a fun fact about the ocean.", session));
Console.WriteLine();

// Run 2: switch to the second registered inner client (model B).
routing.SetActiveDestinationKey(session, modelB);
Console.WriteLine($"[Active model: {routing.GetActiveDestinationKey(session)}]");
Console.WriteLine(await agent.RunAsync("Give me another one, on a different topic.", session));
Console.WriteLine();

// Run 3: switch to a model that is NOT registered as an inner client. The
// fallback factory constructs a client for it on the fly.
routing.SetActiveDestinationKey(session, modelC);
Console.WriteLine($"[Active model: {routing.GetActiveDestinationKey(session)}]");
Console.WriteLine(await agent.RunAsync("And one more, about space.", session));
