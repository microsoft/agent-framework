// Copyright (c) Microsoft. All rights reserved.

// Step 4: Memory
// Add persistent memory so the agent can remember information across sessions.
// Uses ChatHistoryMemoryProvider with an in-memory vector store to recall prior conversations.
//
// For more on conversations, see: ../02-agents/conversations/
// For docs: https://learn.microsoft.com/agent-framework/agents/memory

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";

// <setup_memory>
// Create a vector store for storing chat messages (replace with a persistent store in production).
VectorStore vectorStore = new InMemoryVectorStore(new InMemoryVectorStoreOptions()
{
    EmbeddingGenerator = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
        .GetEmbeddingClient(embeddingDeploymentName)
        .AsIEmbeddingGenerator()
});

AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are good at telling jokes." },
        Name = "Joker",
        AIContextProviderFactory = (ctx, ct) => new ValueTask<AIContextProvider>(new ChatHistoryMemoryProvider(
            vectorStore,
            collectionName: "chathistory",
            vectorDimensions: 3072,
            storageScope: new() { UserId = "UID1", SessionId = Guid.NewGuid().ToString() },
            searchScope: new() { UserId = "UID1" }))
    });
// </setup_memory>

// <use_memory>
// Session 1: Tell the agent what you like
AgentSession session1 = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("I like jokes about Pirates. Tell me a joke about a pirate.", session1));

// Session 2: The agent remembers your preferences from session 1
AgentSession session2 = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke that I might like.", session2));
// </use_memory>
