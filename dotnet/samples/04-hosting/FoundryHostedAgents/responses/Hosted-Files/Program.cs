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
//     container, which the platform sets to /home/session by default.
//
// Each source is exposed via a separate tool pair, each rooted at its own directory.
// Tools take a fileName, not a path: Path.GetFileName strips any directory components,
// then a canonicalize + StartsWith(root) check enforces the boundary.
//
// This sample is deployed to Foundry directly from source (code / ZIP upload), so the
// platform builds and runs your code with no container image.
//
// Required environment variables:
//   FOUNDRY_PROJECT_ENDPOINT          - Foundry project endpoint
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
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var endpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-files";

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
var credential = new DefaultAzureCredential();

// ── File roots (canonicalized once) ──────────────────────────────────────────

// Bundled root: where csproj <Content Include="resources\**"> lands at runtime.
// In the container that resolves to /app/resources/.
string bundledRoot = Path.GetFullPath(
    System.Environment.GetEnvironmentVariable("BUNDLED_FILES_DIR")
    ?? Path.Combine(AppContext.BaseDirectory, "resources"));

// Session root: the per-session $HOME volume mounted by the Foundry platform.
string sessionRoot = Path.GetFullPath(
    System.Environment.GetEnvironmentVariable("HOME")
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
            System.Environment.NewLine,
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
        name: agentName,
        description: "Hosted agent that answers questions over bundled (image-baked) and session-uploaded files via two scoped tool pairs.",
        tools:
        [
            AIFunctionFactory.Create(ListBundledFiles),
            AIFunctionFactory.Create(ReadBundledFile),
            AIFunctionFactory.Create(ListSessionFiles),
            AIFunctionFactory.Create(ReadSessionFile),
        ]);

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;
