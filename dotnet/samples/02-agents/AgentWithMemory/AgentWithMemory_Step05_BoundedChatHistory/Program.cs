// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create a bounded chat history provider that keeps a configurable number of
// recent messages in session state and automatically overflows older messages to a vector store.
// When the agent is invoked, it searches the vector store for relevant older messages and
// prepends them as a "memory" context message before the recent session history.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI.Chat;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var credential = new DefaultAzureCredential();

// Create a vector store to store overflow chat messages.
// For demonstration purposes, we are using an in-memory vector store.
// Replace this with a persistent vector store implementation for production scenarios.
VectorStore vectorStore = new InMemoryVectorStore(new InMemoryVectorStoreOptions()
{
    EmbeddingGenerator = new AzureOpenAIClient(new Uri(endpoint), credential)
        .GetEmbeddingClient(embeddingDeploymentName)
        .AsIEmbeddingGenerator()
});

var sessionId = Guid.NewGuid().ToString();

// Create the BoundedChatHistoryProvider with a maximum of 4 non-system messages in session state.
// It internally creates an InMemoryChatHistoryProvider with a TruncatingChatReducer and a
// ChatHistoryMemoryProvider with the correct configuration to ensure overflow messages are
// automatically archived to the vector store and recalled via semantic search.
var boundedProvider = new BoundedChatHistoryProvider(
    maxSessionMessages: 4,
    vectorStore,
    collectionName: "chathistory-overflow",
    vectorDimensions: 3072,
    session => new ChatHistoryMemoryProvider.State(
        storageScope: new() { UserId = "UID1", SessionId = sessionId },
        searchScope: new() { UserId = "UID1" }));

// Create the agent with the bounded chat history provider.
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), credential)
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are a helpful assistant. Answer questions concisely." },
        Name = "Assistant",
        ChatHistoryProvider = boundedProvider,
    });

// Start a conversation. The first several exchanges will fill up the session state window.
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("--- Filling the session window (4 messages max) ---\n");

Console.WriteLine(await agent.RunAsync("My favorite color is blue.", session));
Console.WriteLine(await agent.RunAsync("I have a dog named Max.", session));

// At this point the session state holds 4 messages (2 user + 2 assistant).
// The next exchange will push the oldest messages into the vector store.
Console.WriteLine("\n--- Next exchange will trigger overflow to vector store ---\n");

Console.WriteLine(await agent.RunAsync("What is the capital of France?", session));

// The oldest messages about favorite color have now been archived to the vector store.
// Ask the agent something that requires recalling the overflowed information.
Console.WriteLine("\n--- Asking about overflowed information (should recall from vector store) ---\n");

Console.WriteLine(await agent.RunAsync("What is my favorite color?", session));
