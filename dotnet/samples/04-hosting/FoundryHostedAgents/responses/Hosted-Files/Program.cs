// Copyright (c) Microsoft. All rights reserved.

// Hosted Files Agent - A hosted agent that exposes two distinct file knowledge sources
// through scoped, security-hardened tools:
//
//   * Bundled files (image-baked) — files copied into the published output via the csproj
//     <Content Include="resources\**"> rule. Live at /app/resources/ inside the container.
//     Author-shipped knowledge that ships with every session.
//
//   * Session files (per-session $HOME volume) — files uploaded at runtime via the alpha
//     Azure.AI.Projects.AgentSessionFiles SDK. Live at $HOME inside the per-session
//     container, which the platform sets to /home/session by default
//     (container-image-spec.md line 127, "If you use the session files API, $HOME is
//     also the base path for those operations").
//
// Each source is exposed via a separate tool pair, each rooted at its own directory.
// Tools take a fileName, not a path: Path.GetFileName strips any directory components,
// then a canonicalize + StartsWith(root) check enforces the boundary. The model cannot
// be tricked into reading /etc/passwd or any path outside its tool's root, even via
// indirect prompt injection in an uploaded file.
//
// Required environment variables:
//   AZURE_AI_PROJECT_ENDPOINT         - Azure AI Foundry project endpoint
//   AZURE_AI_MODEL_DEPLOYMENT_NAME    - Model deployment name (default: gpt-4o)
//
// Optional:
//   AGENT_NAME                        - Agent name (default: hosted-files)
//   BUNDLED_FILES_DIR                 - Override the bundled-files root
//                                       (default: <baseDir>/resources, i.e. /app/resources/)
//   HOME                              - Standard env var; the per-session sandbox volume
//                                       (default: /home/session in the platform-managed container)

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

// Bypass SampleEnvironment alias (which prompts on missing env vars) for optional values.
string? GetOptionalEnv(string key) => System.Environment.GetEnvironmentVariable(key);

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = GetOptionalEnv("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// ── File roots (canonicalized once) ──────────────────────────────────────────

// Bundled root: where csproj <Content Include="resources\**"> lands at runtime.
// In the container that resolves to /app/resources/.
string bundledRoot = Path.GetFullPath(
    GetOptionalEnv("BUNDLED_FILES_DIR")
    ?? Path.Combine(AppContext.BaseDirectory, "resources"));

// Session root: the per-session $HOME volume mounted by the Foundry platform.
// Files uploaded via AgentSessionFiles.UploadSessionFileAsync(sessionStoragePath: "foo")
// land at $HOME/foo per container-image-spec.md line 172.
string sessionRoot = Path.GetFullPath(
    GetOptionalEnv("HOME")
    ?? "/home/session");

// ── Tools: bundled files (image-baked, /app/resources/) ──────────────────────

[Description("List the names of files bundled with the agent (built-in knowledge that ships with the image).")]
string ListBundledFiles() => SafeListNames(bundledRoot);

[Description("Read the full text contents of a bundled file by name. Bundled files are built-in knowledge shipped with the agent image.")]
string ReadBundledFile(
    [Description("Name of the bundled file (no directory components). Must be one of the names returned by ListBundledFiles.")] string fileName)
    => SafeRead(bundledRoot, fileName, scope: "bundled files");

// ── Tools: session files (per-session $HOME) ─────────────────────────────────

[Description("List the names of files uploaded into the current session sandbox by the user (e.g., via AgentSessionFiles.UploadSessionFileAsync).")]
string ListSessionFiles() => SafeListNames(sessionRoot);

[Description("Read the full text contents of a file uploaded into the current session by name. Session files are user-supplied data that lives only for the lifetime of this session.")]
string ReadSessionFile(
    [Description("Name of the session file (no directory components). Must be one of the names returned by ListSessionFiles.")] string fileName)
    => SafeRead(sessionRoot, fileName, scope: "session files");

// ── Path-safe helpers (defense-in-depth: GetFileName + canonicalize + StartsWith(root)) ──

string SafeListNames(string root)
{
    try
    {
        if (!Directory.Exists(root))
        {
            return string.Empty;
        }

        return string.Join(
            Environment.NewLine,
            Directory.EnumerateFiles(root).Select(Path.GetFileName));
    }
    catch (Exception ex)
    {
        return $"Error listing files: {ex.Message}";
    }
}

string SafeRead(string root, string fileName, string scope)
{
    try
    {
        // Step 1: strip any directory components the model might have included.
        string safeName = Path.GetFileName(fileName);
        if (string.IsNullOrEmpty(safeName))
        {
            return $"File '{fileName}' not found in {scope}.";
        }

        // Step 2: combine with the root and canonicalize.
        string fullPath = Path.GetFullPath(Path.Combine(root, safeName));

        // Step 3: enforce the prefix boundary so a crafted name still cannot escape.
        string rootPrefix = root.EndsWith(Path.DirectorySeparatorChar)
            ? root
            : root + Path.DirectorySeparatorChar;
        if (!fullPath.StartsWith(rootPrefix, StringComparison.Ordinal))
        {
            return $"File '{fileName}' not found in {scope}.";
        }

        return File.Exists(fullPath)
            ? File.ReadAllText(fullPath)
            : $"File '{fileName}' not found in {scope}.";
    }
    catch (Exception ex)
    {
        return $"Error reading '{fileName}': {ex.Message}";
    }
}

// ── Create and host the agent ────────────────────────────────────────────────

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
    .AsAIAgent(
        model: deploymentName,
        instructions: """
            You are a friendly assistant that answers questions over two file sources:

              - Bundled files: built-in knowledge that ships with the agent image
                (e.g., reference reports the author packaged with you). Tools:
                ListBundledFiles, ReadBundledFile.

              - Session files: user-uploaded data for this session only (e.g., a CSV
                the user wants you to analyse). Tools: ListSessionFiles, ReadSessionFile.

            Pick the tool pair by intent. If a name could match either source, list
            both first. Always read the file before answering; do not guess. Quote
            numbers and figures verbatim from the file.
            """,
        name: GetOptionalEnv("AGENT_NAME") ?? "hosted-files",
        description: "Hosted agent that answers questions over bundled (image-baked) and session-uploaded files via two scoped tool pairs.",
        tools:
        [
            AIFunctionFactory.Create(ListBundledFiles),
            AIFunctionFactory.Create(ReadBundledFile),
            AIFunctionFactory.Create(ListSessionFiles),
            AIFunctionFactory.Create(ReadSessionFile),
        ]);

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

if (app.Environment.IsDevelopment())
{
    app.MapFoundryResponses("openai/v1");
}

app.Run();

/// <summary>
/// A <see cref="TokenCredential"/> for local Docker debugging only.
/// Reads a pre-fetched bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable
/// once at startup. This should NOT be used in production.
///
/// Generate a token on your host and pass it to the container:
///   export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN ...
/// </summary>
internal sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string EnvironmentVariable = "AZURE_BEARER_TOKEN";
    private readonly string? _token;

    public DevTemporaryTokenCredential()
    {
        this._token = System.Environment.GetEnvironmentVariable(EnvironmentVariable);
    }

    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => this.GetAccessToken();

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        => new(this.GetAccessToken());

    private AccessToken GetAccessToken()
    {
        if (string.IsNullOrEmpty(this._token) || this._token == "DefaultAzureCredential")
        {
            throw new CredentialUnavailableException($"{EnvironmentVariable} environment variable is not set.");
        }

        return new AccessToken(this._token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
