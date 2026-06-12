// Copyright (c) Microsoft. All rights reserved.

// Hosted-AgentSkills
//
// Demonstrates how to host an agent that loads its behavioral guidelines from Foundry Skills at
// startup. Skills are authored as SKILL.md files, uploaded to Foundry via the Skills REST API,
// and downloaded by the agent on boot so guideline updates ship without code changes.
//
// The agent uses AgentSkillsProvider from the Agent Framework which implements the progressive
// disclosure pattern from the Agent Skills specification (https://agentskills.io/):
//   1. Advertise — skill names and descriptions are injected into the system prompt.
//   2. Load — the model calls load_skill to retrieve the full SKILL.md body on demand.
//
// IMPORTANT: In production, skill provisioning (uploading SKILL.md files to Foundry) is an
// external concern — it is NOT the hosted agent's responsibility. The provisioning helper below
// is included for sample convenience only, so the sample is self-contained and runnable without
// a separate setup step. A real deployment pipeline would provision skills separately (e.g., via
// a CI/CD step, a CLI script, or a management portal).

#pragma warning disable AAIP001 // ProjectAgentSkills is experimental

using System.ClientModel;
using System.IO.Compression;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";
string skillNames = Environment.GetEnvironmentVariable("SKILL_NAMES")
    ?? throw new InvalidOperationException("SKILL_NAMES is not set. Provide a comma-separated list of skill names (e.g., support-style,escalation-policy).");

string[] requestedSkills = skillNames.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
if (requestedSkills.Length == 0)
{
    throw new InvalidOperationException("SKILL_NAMES must list at least one skill name.");
}

// Validate skill names to prevent path traversal.
foreach (string name in requestedSkills)
{
    if (name.Contains('.') || name.Contains('/') || name.Contains('\\') || Path.IsPathRooted(name))
    {
        throw new InvalidOperationException(
            $"Invalid skill name '{name}': skill names must not contain path separators or dots.");
    }
}

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
// Use a chained credential: try a temporary dev token first (for local Docker debugging),
// then fall back to DefaultAzureCredential (for local dev via dotnet run / managed identity in production).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

AIProjectClient projectClient = new(new Uri(endpoint), credential);
ProjectAgentSkills skillsClient = projectClient.AgentAdministrationClient.GetAgentSkills();

// ── Provision skills (sample convenience only — NOT a production pattern) ─────
// In production, skills are provisioned externally (e.g., via CI/CD or a management script).
// This helper ensures the sample's SKILL.md files exist in Foundry so the sample is runnable
// out of the box without a separate setup step. Set PROVISION_SAMPLE_SKILLS=true to enable.
string sourceSkillsDir = Path.Combine(AppContext.BaseDirectory, "skills");
bool provisionEnabled = string.Equals(
    Environment.GetEnvironmentVariable("PROVISION_SAMPLE_SKILLS"), "true", StringComparison.OrdinalIgnoreCase);
if (provisionEnabled && Directory.Exists(sourceSkillsDir))
{
    await EnsureSkillsProvisionedAsync(skillsClient, sourceSkillsDir, requestedSkills);
}

// ── Download skills from Foundry ─────────────────────────────────────────────
// Pull the latest copy of each skill from Foundry into a runtime-only folder.
// This directory is recreated on every startup so the agent always picks up
// the latest version of each skill.
string downloadedSkillsDir = Path.Combine(AppContext.BaseDirectory, "downloaded_skills");
await DownloadSkillsAsync(skillsClient, requestedSkills, downloadedSkillsDir);

// ── Wire skills into the agent ───────────────────────────────────────────────
// AgentSkillsProvider implements progressive disclosure: skill names and descriptions
// are advertised in the system prompt (~100 tokens per skill), and the full SKILL.md
// body is loaded on demand when the model calls the load_skill tool.
AgentSkillsProvider skillsProvider = new(downloadedSkillsDir);

ChatClientAgent agent = projectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-agent-skills",
    ChatOptions = new ChatOptions
    {
        ModelId = deploymentName,
        Instructions = "You are a customer-support assistant for Contoso Outdoors.",
    },
    AIContextProviders = [skillsProvider]
});

// Host the agent as a Foundry Hosted Agent using the Responses API.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);
builder.Services.AddDevTemporaryLocalContributorSetup(); // Local Docker debugging only - must not be used in production.

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();

// ── Helpers ──────────────────────────────────────────────────────────────────

// Downloads each named skill from Foundry and extracts the ZIP archive into a
// separate subdirectory under the target directory.
static async Task DownloadSkillsAsync(ProjectAgentSkills skillsClient, string[] skillNames, string targetDir)
{
    if (Directory.Exists(targetDir))
    {
        Directory.Delete(targetDir, recursive: true);
    }

    Directory.CreateDirectory(targetDir);

    foreach (string name in skillNames)
    {
        Console.WriteLine($"Downloading skill '{name}' from Foundry...");
        BinaryData zipData = await skillsClient.DownloadSkillAsync(name);

        string skillDir = Path.Combine(targetDir, name);
        Directory.CreateDirectory(skillDir);

        using var zipStream = zipData.ToStream();
        using var archive = new ZipArchive(zipStream, ZipArchiveMode.Read);
        SafeExtractZip(archive, skillDir);

        if (!File.Exists(Path.Combine(skillDir, "SKILL.md")))
        {
            throw new InvalidOperationException(
                $"Downloaded archive for '{name}' did not contain a SKILL.md at the root.");
        }
    }
}

// Extracts a ZIP archive into a destination directory, rejecting entries that would
// escape the target path (zip-slip guard).
static void SafeExtractZip(ZipArchive archive, string destinationDir)
{
    string destRoot = Path.GetFullPath(destinationDir);
    string destRootWithSep = Path.EndsInDirectorySeparator(destRoot)
        ? destRoot
        : destRoot + Path.DirectorySeparatorChar;

    // Use ordinal comparison on Unix (case-sensitive FS) and ordinal-ignore-case on Windows.
    var comparison = OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;

    foreach (ZipArchiveEntry entry in archive.Entries)
    {
        string entryPath = Path.GetFullPath(Path.Combine(destRoot, entry.FullName));
        if (!entryPath.StartsWith(destRootWithSep, comparison)
            && !string.Equals(entryPath, destRoot, comparison))
        {
            throw new InvalidOperationException(
                $"Refusing to extract unsafe path '{entry.FullName}' outside of '{destRoot}'.");
        }

        if (string.IsNullOrEmpty(entry.Name))
        {
            // Directory entry — ensure it exists.
            Directory.CreateDirectory(entryPath);
        }
        else
        {
            Directory.CreateDirectory(Path.GetDirectoryName(entryPath)!);
            entry.ExtractToFile(entryPath, overwrite: true);
        }
    }
}

// Ensures each requested skill is provisioned in Foundry. For each skill name, checks whether
// the skill exists and uploads it from the local source directory if it does not.
//
// This is a sample convenience helper — in production, skill provisioning is an external concern.
static async Task EnsureSkillsProvisionedAsync(ProjectAgentSkills skillsClient, string sourceDir, string[] skillNames)
{
    foreach (string name in skillNames)
    {
        string skillPath = Path.Combine(sourceDir, name);
        if (!Directory.Exists(skillPath) || !File.Exists(Path.Combine(skillPath, "SKILL.md")))
        {
            continue; // No local source for this skill — skip provisioning.
        }

        try
        {
            await skillsClient.GetSkillAsync(name);
            Console.WriteLine($"Skill '{name}' already exists in Foundry.");
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            Console.WriteLine($"Provisioning skill '{name}' from {skillPath}...");
            AgentsSkill imported = await skillsClient.CreateSkillFromPackageAsync(skillPath);
            Console.WriteLine($"  Imported skill '{imported.Name}' (id={imported.SkillId}, has_blob={imported.HasBlob}).");
        }
    }
}
