// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to give an agent file-based memory using the FileMemoryProvider.
// The FileMemoryProvider exposes a set of tools to the agent (write, read, delete, list, grep and replace)
// that allow it to store memories as individual files in an AgentFileStore.
// Because the files are stored outside of the conversation, the agent can recall them
// in later conversations, even after the original chat history is gone.
//
// The sample also shows how to control the folder that memory files are written to,
// by supplying a state initializer callback that sets the working folder for each session.

#pragma warning disable MAAI001 // AgentFileStore and its implementations are experimental.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// The id of the user that we are storing memories for.
// It is used below to give each user their own memory folder.
const string UserId = "UID1";

// Create the file store that the FileMemoryProvider will use to persist memory files.
// Here we use a file system backed store rooted at a local folder called "agent-memory",
// but any AgentFileStore implementation can be used, e.g. InMemoryAgentFileStore or a custom
// implementation backed by blob storage.
var memoryRoot = Path.Combine(AppContext.BaseDirectory, "agent-memory");
var fileStore = new FileSystemAgentFileStore(memoryRoot);

// The working folder that memories for this user will be written to, relative to the store root.
// The folder you choose determines the scope and lifetime of the memories:
// - A stable folder, like the per-user one below, gives you durable memories that are shared by
//   every session for that user. That is what allows the second conversation further down to
//   recall what the user said in the first.
// - A unique folder per session gives you memories that are isolated to a single session, e.g.
//   generate one in the state initializer callback below:
//       _ => new FileMemoryState { WorkingFolder = Guid.NewGuid().ToString() }
var workingFolder = $"users/{UserId}";

Console.WriteLine($"Memory files will be written to: {Path.Combine(memoryRoot, workingFolder)}");
Console.WriteLine();

// Create the file memory provider.
// The second parameter is a state initializer callback that is invoked whenever the provider
// cannot find existing state in a session, i.e. typically the first time it is used with a new session.
// It allows us to configure the folder that memory files for that session are written to.
// If no callback is supplied, the working folder defaults to the root of the store,
// which means all sessions share a single, flat set of memory files.
using var fileMemoryProvider = new FileMemoryProvider(
    fileStore,
    _ => new FileMemoryState { WorkingFolder = workingFolder });

// Create the agent and attach the FileMemoryProvider so that the agent gets the file memory tools.
AIAgent agent = new AIProjectClient(
        new Uri(endpoint),
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful travel assistant. Remember what the user tells you about themselves so that you can give better recommendations later."
        },
        Name = "TravelAssistant",
        AIContextProviders = [fileMemoryProvider],
    });

// First conversation: tell the agent something worth remembering.
// The agent should use the file_memory_write tool to store it as a file in the working folder.
AgentSession firstSession = await agent.CreateSessionAsync();
Console.WriteLine("=== First conversation ===");
Console.WriteLine(await agent.RunAsync(
    "I'm vegetarian and I always travel with my dog. Please remember this for future trips.",
    firstSession));
Console.WriteLine();

// Show the memory files that the agent created on disk.
Console.WriteLine("=== Memory files on disk ===");
foreach (var file in Directory.EnumerateFiles(Path.Combine(memoryRoot, workingFolder)))
{
    Console.WriteLine(Path.GetFileName(file));
}

Console.WriteLine();

// Second conversation: a brand new session with no chat history from the first conversation.
// The provider surfaces the memory index to the agent, and the agent can read the memory files
// using the file_memory_read tool, so it can still recall the user's preferences.
AgentSession secondSession = await agent.CreateSessionAsync();
Console.WriteLine("=== Second conversation (new session) ===");
Console.WriteLine(await agent.RunAsync(
    "Suggest a hotel and a restaurant for my trip to Paris next week.",
    secondSession));
