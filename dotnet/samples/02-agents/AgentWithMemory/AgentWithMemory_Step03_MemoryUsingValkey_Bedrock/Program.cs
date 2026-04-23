// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using Valkey for both persistent chat history and long-term memory
// context with the Agent Framework, powered by Amazon Bedrock.
//
// Prerequisites:
//   - Valkey 9.1+ with valkey-search module (for the context provider):
//       docker run -d --name valkey -p 6379:6379 valkey/valkey-bundle:9.1.0-rc1
//   - AWS credentials configured (environment variables, AWS profile, or IAM role)
//   - Access to an Amazon Bedrock model (e.g., Anthropic Claude)

using Amazon;
using Amazon.BedrockRuntime;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Valkey;
using Microsoft.Extensions.AI;

var awsRegion = Environment.GetEnvironmentVariable("AWS_REGION") ?? "us-east-1";
var modelId = Environment.GetEnvironmentVariable("BEDROCK_MODEL_ID") ?? "anthropic.claude-3-5-sonnet-20241022-v2:0";
var valkeyConnection = Environment.GetEnvironmentVariable("VALKEY_CONNECTION") ?? "localhost:6379";

// Create the Bedrock runtime client.
// Uses the default credential chain: env vars, AWS profile, IAM role, etc.
var bedrockRuntime = new AmazonBedrockRuntimeClient(RegionEndpoint.GetBySystemName(awsRegion));
IChatClient chatClient = bedrockRuntime.AsIChatClient(modelId);

// --- Part 1: Chat History with ValkeyChatHistoryProvider ---
Console.WriteLine("=== Part 1: ValkeyChatHistoryProvider — Persistent Chat History (Bedrock) ===\n");

await using var historyProvider = new ValkeyChatHistoryProvider(
    valkeyConnection,
    stateInitializer: _ => new ValkeyChatHistoryProvider.State($"bedrock-sample-{Guid.NewGuid():N}"),
    keyPrefix: "bedrock_chat")
{
    MaxMessages = 20
};

AIAgent historyAgent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    ChatOptions = new() { Instructions = "You are a helpful assistant that remembers our conversation." },
    ChatHistoryProvider = historyProvider
});

AgentSession session1 = await historyAgent.CreateSessionAsync();
Console.WriteLine(await historyAgent.RunAsync("Hello! My name is Alex and I'm a software engineer.", session1));
Console.WriteLine(await historyAgent.RunAsync("I'm working on a project using Valkey for caching.", session1));
Console.WriteLine(await historyAgent.RunAsync("What do you remember about me?", session1));

var messageCount = await historyProvider.GetMessageCountAsync(session1);
Console.WriteLine($"\n  Stored {messageCount} messages in Valkey.\n");

// --- Part 2: Context Provider with ValkeyContextProvider ---
Console.WriteLine("=== Part 2: ValkeyContextProvider — Long-Term Memory (Bedrock) ===\n");

await using var contextProvider = new ValkeyContextProvider(
    valkeyConnection,
    stateInitializer: _ => new ValkeyContextProvider.State(
        new ValkeyProviderScope { ApplicationId = "bedrock-sample-app", UserId = "sample-user" }),
    indexName: "bedrock_memory_idx",
    keyPrefix: "bedrock_mem:");

AIAgent memoryAgent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    ChatOptions = new() { Instructions = "You are a friendly assistant. Use known memories about the user when responding." },
    AIContextProviders = [contextProvider]
});

// Conversation 1 — store some facts
AgentSession memSession1 = await memoryAgent.CreateSessionAsync();
Console.WriteLine("[Conversation 1] Storing facts...");
Console.WriteLine(await memoryAgent.RunAsync("I'm planning a trip to Japan in December. I love sushi and hiking.", memSession1));
Console.WriteLine(await memoryAgent.RunAsync("My favorite programming language is C# and I use .NET daily.", memSession1));

// Conversation 2 — new session, agent should recall from Valkey
AgentSession memSession2 = await memoryAgent.CreateSessionAsync();
Console.WriteLine("\n[Conversation 2] Testing recall across sessions...");
Console.WriteLine(await memoryAgent.RunAsync("What do you know about my upcoming travel plans?", memSession2));

Console.WriteLine("\nDone!");
