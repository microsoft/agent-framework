// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure;
using Azure.AI.Projects;
using Azure.Identity;
using Azure.Search.Documents;
using Azure.Search.Documents.Models;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Foundry hosted agent test container for Foundry.Hosting.IntegrationTests.
//
// One image, many scenarios. The IT_SCENARIO environment variable selects which agent
// behavior is wired up at startup. Each scenario corresponds to one test fixture and
// one set of tests in the IT project.
//
// The platform injects FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME, FOUNDRY_AGENT_VERSION,
// PORT, and APPLICATIONINSIGHTS_CONNECTION_STRING. We never set FOUNDRY_* or AGENT_* names
// from the test side because they are reserved by the platform.

var scenario = Environment.GetEnvironmentVariable("IT_SCENARIO") ?? "happy-path";
var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

var projectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

AIAgent agent = scenario switch
{
    "happy-path" => CreateHappyPathAgent(projectClient, deployment),
    "tool-calling" => CreateToolCallingAgent(projectClient, deployment),
    "tool-calling-approval" => CreateToolCallingApprovalAgent(projectClient, deployment),
    "mcp-toolbox" => CreateMcpToolboxAgent(projectClient, deployment),
    "custom-storage" => CreateCustomStorageAgent(projectClient, deployment),
    "azure-search-rag" => CreateAzureSearchRagAgent(projectClient, deployment),
    "session-files" => CreateSessionFilesAgent(projectClient, deployment),
    _ => throw new InvalidOperationException($"Unknown IT_SCENARIO '{scenario}'.")
};

var builder = WebApplication.CreateBuilder(args);

var port = Environment.GetEnvironmentVariable("PORT");
if (!string.IsNullOrEmpty(port))
{
    builder.WebHost.UseUrls($"http://+:{port}");
}

builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();
app.MapGet("/readiness", () => Results.Ok());
app.Run();

static AIAgent CreateHappyPathAgent(AIProjectClient client, string deployment) =>
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful AI assistant. Always reply with exactly the single word ECHO unless the user explicitly asks a question that requires a different answer.",
        name: "happy-path-agent",
        description: "Round trip and conversation test agent.");

static AIAgent CreateToolCallingAgent(AIProjectClient client, string deployment) =>
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant. Use the GetUtcNow and Multiply tools when appropriate.",
        name: "tool-calling-agent",
        description: "Server side tool calling test agent.",
        tools: [
            AIFunctionFactory.Create(GetUtcNow),
            AIFunctionFactory.Create(Multiply)
        ]);

static AIAgent CreateToolCallingApprovalAgent(AIProjectClient client, string deployment) =>
    // TODO: wire approval required AIFunction once the public surface is finalized.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant. Use the SendEmail tool when asked to send a message; it requires user approval before running.",
        name: "tool-calling-approval-agent",
        description: "Approval flow test agent (placeholder).",
        tools: [
            AIFunctionFactory.Create(SendEmail)
        ]);

static AIAgent CreateMcpToolboxAgent(AIProjectClient client, string deployment) =>
    // TODO: wire MCP toolbox client to https://learn.microsoft.com/api/mcp.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are an assistant with access to Microsoft Learn documentation via MCP.",
        name: "mcp-toolbox-agent",
        description: "MCP toolbox test agent (placeholder).");

static AIAgent CreateCustomStorageAgent(AIProjectClient client, string deployment) =>
    // TODO: substitute custom IResponsesStorageProvider in DI.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant.",
        name: "custom-storage-agent",
        description: "Custom storage test agent (placeholder).");

static AIAgent CreateAzureSearchRagAgent(AIProjectClient client, string deployment)
{
    // The fixture (AzureSearchRagHostedAgentFixture) injects AZURE_SEARCH_ENDPOINT and
    // AZURE_SEARCH_INDEX_NAME into the hosted agent definition. The index is provisioned
    // out of band (see dotnet/tests/Foundry.Hosting.IntegrationTests/README.md for the
    // required schema and seed content); the container only needs read access. The
    // agent's managed identity must hold 'Search Index Data Reader' on the search service
    // scope.
    var searchEndpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_SEARCH_ENDPOINT")
        ?? throw new InvalidOperationException("AZURE_SEARCH_ENDPOINT is not set for IT_SCENARIO=azure-search-rag."));
    var indexName = Environment.GetEnvironmentVariable("AZURE_SEARCH_INDEX_NAME")
        ?? throw new InvalidOperationException("AZURE_SEARCH_INDEX_NAME is not set for IT_SCENARIO=azure-search-rag.");

    var searchClient = new SearchClient(searchEndpoint, indexName, new DefaultAzureCredential());

    var options = new TextSearchProviderOptions
    {
        SearchTime = TextSearchProviderOptions.TextSearchBehavior.BeforeAIInvoke,
        RecentMessageMemoryLimit = 6,
    };

    return client.AsAIAgent(new ChatClientAgentOptions
    {
        Name = "azure-search-rag-agent",
        ChatOptions = new ChatOptions
        {
            ModelId = deployment,
            Instructions = "You are a helpful support specialist for Contoso Outdoors. " +
                           "Answer questions using the provided context and cite the source document when available.",
        },
        AIContextProviders = [new TextSearchProvider(CreateAzureSearchAdapter(searchClient), options)]
    });
}

static Func<string, CancellationToken, Task<IEnumerable<TextSearchProvider.TextSearchResult>>>
    CreateAzureSearchAdapter(SearchClient client, int top = 3) =>
    async (query, cancellationToken) =>
    {
        var searchOptions = new SearchOptions { Size = top };
        Response<SearchResults<SearchDocument>> response =
            await client.SearchAsync<SearchDocument>(query, searchOptions, cancellationToken).ConfigureAwait(false);

        var results = new List<TextSearchProvider.TextSearchResult>();
        await foreach (SearchResult<SearchDocument> hit in response.Value.GetResultsAsync().WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            results.Add(new TextSearchProvider.TextSearchResult
            {
                SourceName = hit.Document.TryGetValue("sourceName", out var name) ? name?.ToString() ?? string.Empty : string.Empty,
                SourceLink = hit.Document.TryGetValue("sourceLink", out var link) ? link?.ToString() ?? string.Empty : string.Empty,
                Text = hit.Document.TryGetValue("content", out var content) ? content?.ToString() ?? string.Empty : string.Empty,
                RawRepresentation = hit
            });
        }

        return results;
    };
// session-files scenario: agent reads files from $HOME inside the per-session sandbox volume.
// Mirrors the dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Files sample.
static AIAgent CreateSessionFilesAgent(AIProjectClient client, string deployment) =>
    client.AsAIAgent(
        model: deployment,
        instructions: """
            You are a friendly assistant that helps users inspect and summarise
            files stored in the session sandbox at $HOME.

            Always answer file-related questions by calling the available tools
            (GetHomeDirectory, ListFiles, ReadFile). Do not guess file paths or
            contents — read the file before answering.

            Quote numbers and figures verbatim from the file rather than
            paraphrasing them.
            """,
        name: "session-files-agent",
        description: "Reads files from the per-session $HOME volume.",
        tools: [
            AIFunctionFactory.Create(GetHomeDirectory),
            AIFunctionFactory.Create(ListFiles),
            AIFunctionFactory.Create(ReadFile)
        ]);

[Description("Returns the current UTC date and time as an ISO 8601 string.")]
static string GetUtcNow() => DateTime.UtcNow.ToString("o");

[Description("Multiplies two integers and returns the product.")]
static int Multiply([Description("First operand")] int a, [Description("Second operand")] int b) => a * b;

[Description("Sends an email. Requires user approval.")]
static string SendEmail(
    [Description("Recipient address")] string to,
    [Description("Email subject")] string subject) =>
    $"Email sent to {to} with subject '{subject}'.";

// session-files tools: resolve paths against $HOME (the per-session sandbox volume).
[Description("Get the absolute path of the session home directory ($HOME).")]
static string GetHomeDirectory() => SessionHome();

[Description("List files and directories under the given path inside the session sandbox. Pass an empty string to list $HOME.")]
static string[] ListFiles(
    [Description("Path relative to $HOME. Absolute paths and traversals (..) are rejected.")] string path)
{
    try
    {
        return Directory.EnumerateFileSystemEntries(ResolveSessionPath(path)).ToArray();
    }
    catch (Exception ex)
    {
        return [$"Error listing '{path}': {ex.Message}"];
    }
}

[Description("Read the full text contents of a file inside the session sandbox.")]
static string ReadFile(
    [Description("Path relative to $HOME. Absolute paths and traversals (..) are rejected.")] string path)
{
    try
    {
        return File.ReadAllText(ResolveSessionPath(path));
    }
    catch (Exception ex)
    {
        return $"Error reading '{path}': {ex.Message}";
    }
}

static string SessionHome() =>
    Environment.GetEnvironmentVariable("HOME")
    ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

// Resolve a caller-supplied path against $HOME, rejecting absolute paths and traversal segments
// so that the model cannot read or list arbitrary container files via the ReadFile/ListFiles
// tools (defense-in-depth against indirect prompt injection). Mirrors the canonicalize +
// startsWith($HOME) pattern used by FileSystemAgentFileStore.ResolveSafePath.
static string ResolveSessionPath(string path)
{
    string home = SessionHome();
    string homeFull = Path.GetFullPath(home);
    string homePrefix = homeFull.EndsWith(Path.DirectorySeparatorChar)
        ? homeFull
        : homeFull + Path.DirectorySeparatorChar;

    if (string.IsNullOrWhiteSpace(path))
    {
        return homeFull;
    }

    if (Path.IsPathRooted(path))
    {
        throw new ArgumentException($"Absolute paths are not allowed: '{path}'.", nameof(path));
    }

    string combined = Path.Combine(homeFull, path);
    string fullPath = Path.GetFullPath(combined);

    if (!fullPath.Equals(homeFull, StringComparison.Ordinal) &&
        !fullPath.StartsWith(homePrefix, StringComparison.Ordinal))
    {
        throw new ArgumentException(
            $"Path '{path}' resolves outside the session sandbox.", nameof(path));
    }

    return fullPath;
}
