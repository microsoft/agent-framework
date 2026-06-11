// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using Valkey for persistent chat history with the Agent Framework,
// powered by Amazon Bedrock.
//
// Prerequisites:
//   - A running Valkey server (any version):
//       docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
//   - AWS credentials configured (environment variables, AWS profile, or IAM role)
//   - Access to an Amazon Bedrock model (e.g., Anthropic Claude)

using Amazon;
using Amazon.BedrockRuntime;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Valkey;
using Microsoft.Extensions.AI;
using Valkey.Glide;

var awsRegion = Environment.GetEnvironmentVariable("AWS_REGION") ?? "us-east-1";
var modelId = Environment.GetEnvironmentVariable("BEDROCK_MODEL_ID") ?? "anthropic.claude-3-5-sonnet-20241022-v2:0";
var valkeyConnection = Environment.GetEnvironmentVariable("VALKEY_CONNECTION") ?? "localhost:6379";

// Create the Bedrock runtime client.
var bedrockRuntime = new AmazonBedrockRuntimeClient(RegionEndpoint.GetBySystemName(awsRegion));
IChatClient chatClient = bedrockRuntime.AsIChatClient(modelId);

var connection = await ConnectionMultiplexer.ConnectAsync(valkeyConnection);

Console.WriteLine("=== ValkeyChatHistoryProvider — Persistent Chat History (Bedrock) ===\n");

var historyProvider = new ValkeyChatHistoryProvider(
    connection,
    _ => new ValkeyChatHistoryProvider.State($"bedrock-sample-{Guid.NewGuid():N}"),
    new ValkeyChatHistoryProviderOptions
    {
        KeyPrefix = "bedrock_chat",
        MaxMessages = 20
    });

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

// Clean up
connection.Dispose();

Console.WriteLine("Done!");
