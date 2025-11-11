// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent that stores chat messages in a vector store using the ChatHistoryMemoryProvider.
// It can then use the chat history from prior conversations to inform responses in new conversations.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;
using Microsoft.SemanticKernel.Connectors.InMemory;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") ?? "text-embedding-3-large";

// Create a vector store to store the chat messages in.
// For demonstration purposes, we are using an in-memory vector store.
// Replace this with a vector store implementation of your choice that can persist the chat history long term.
VectorStore vectorStore = new InMemoryVectorStore(new InMemoryVectorStoreOptions()
{
    EmbeddingGenerator = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
        .GetEmbeddingClient(embeddingDeploymentName)
        .AsIEmbeddingGenerator()
});

// Create the agent and add the ChatHistoryMemoryProvider to store chat messages in the vector store.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions
    {
        Instructions = "You are good at telling jokes.",
        Name = "Joker",
        AIContextProviderFactory = (ctx) => new ChatHistoryMemoryProvider(
            vectorStore,
            collectionName: "chathistory",
            vectorDimensions: 3072,
            // Configure the scope values under which chat messages will be stored.
            // In this case, we are using a fixed user ID and a unique thread ID for each new thread.
            storageScope: new() { UserId = "UID1", ThreadId = new Guid().ToString() },
            // Configure the scope which would be used to search for relevant prior messages.
            // In this case, we are searching for any messages for the user across all threads.
            searchScope: new() { UserId = "UID1" })
    });

// Start a new thread for the agent conversation.
AgentThread thread = agent.GetNewThread();

// Run the agent with the thread that stores conversation history in the vector store.
Console.WriteLine(await agent.RunAsync("I like jokes about Pirates. Tell me a joke about a pirate.", thread));

// Start a second thread. Since we configured the search scope to be across all threads for the user,
// the agent should remember that the user likes pirate jokes.
AgentThread thread2 = agent.GetNewThread();

// Run the agent with the second thread.
Console.WriteLine(await agent.RunAsync("Tell me a joke that I might like.", thread2));
