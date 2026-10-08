// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// Discovers skills through the MCP <c>skills/list</c> method.
/// </summary>
/// <remarks>
/// Instructions and resources are fetched later, when requested.
/// </remarks>
internal sealed class McpListedSkillsLoader
{
    private const string CompleteResultType = "complete";

    private readonly McpClient _client;

    /// <summary>
    /// Initializes a loader for skills discovered through <c>skills/list</c>.
    /// </summary>
    /// <param name="client">The MCP client used to discover skills and fetch their content.</param>
    public McpListedSkillsLoader(McpClient client)
    {
        this._client = Throw.IfNull(client);
    }

    /// <summary>
    /// Gets the server's listed skills without fetching their instructions or resources.
    /// </summary>
    /// <param name="cancellationToken">The token used to cancel discovery.</param>
    /// <returns>The skills discovered through <c>skills/list</c>.</returns>
    public async Task<IList<AgentSkill>> DiscoverAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();

        JsonRpcResponse response = await this._client.SendRequestAsync(new JsonRpcRequest
        {
            Method = "skills/list",
            Params = new JsonObject(),
        }, cancellationToken).ConfigureAwait(false);

        McpSkillsListResult result = response.Result?.Deserialize(McpListedSkillsJsonContext.Default.McpSkillsListResult)
            ?? throw new JsonException("The server returned no skills/list result.");

        if (result.ResultType != CompleteResultType)
        {
            throw new JsonException($"A skills/list result must have resultType '{CompleteResultType}'. Received resultType '{result.ResultType}'.");
        }

        List<AgentSkill> skills = [];

        foreach (McpListedSkillEntry? entry in result.Skills)
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Nullable annotations do not reject null collection elements during deserialization.
            if (entry is null)
            {
                throw new JsonException("The skills/list result contains a null skill entry.");
            }

            AgentSkillFrontmatter frontmatter = CreateFrontmatter(entry);

            List<McpListedSkillResourceEntry> resources = CreateSupportingResources(entry);

            skills.Add(new AgentMcpListedSkill(frontmatter, entry.Uri, resources, this._client));
        }

        return skills;
    }

    private static AgentSkillFrontmatter CreateFrontmatter(McpListedSkillEntry entry)
    {
        // Instructions must be addressable as a safe, absolute resource, e.g. skill://unit-converter/SKILL.md.
        if (!Uri.TryCreate(entry.Uri, UriKind.Absolute, out _) ||
            !entry.Uri.EndsWith("/SKILL.md", StringComparison.Ordinal) ||
            entry.Uri.Contains('\\') || entry.Uri.Any(char.IsControl))
        {
            throw new JsonException("A skill entry must specify an absolute SKILL.md resource URI.");
        }

        // Validate the metadata needed to advertise the skill.
        if (!AgentSkillFrontmatter.ValidateName(entry.Frontmatter.Name, out string? reason) ||
            !AgentSkillFrontmatter.ValidateDescription(entry.Frontmatter.Description, out reason))
        {
            throw new JsonException($"Skill '{entry.Uri}' has invalid frontmatter: {reason}");
        }

        // skill://unit-converter/SKILL.md -> skill://unit-converter
        string directory = entry.Uri[..^"/SKILL.md".Length];

        // Start of "unit-converter" in skill://unit-converter; 0 if no '/'.
        int segmentStart = directory.LastIndexOf('/') + 1;

        // Opaque URI schemes can place the skill name directly after the scheme.
        if (segmentStart == 0)
        {
            // Start of "unit-converter" in skill:unit-converter.
            segmentStart = directory.IndexOf(':') + 1;
        }

        // directory[segmentStart..] extracts "unit-converter", which must match the advertised skill name.
        if (!string.Equals(directory[segmentStart..], entry.Frontmatter.Name, StringComparison.Ordinal))
        {
            throw new JsonException($"Skill URI '{entry.Uri}' must end with its frontmatter name followed by /SKILL.md.");
        }

        // Project the fields used to advertise the skill.
        return new AgentSkillFrontmatter(entry.Frontmatter.Name, entry.Frontmatter.Description);
    }

    private static List<McpListedSkillResourceEntry> CreateSupportingResources(McpListedSkillEntry entry)
    {
        string skillUri = entry.Uri;

        // skill://unit-converter/SKILL.md -> skill://unit-converter/ (keep the trailing slash).
        string skillRootUri = skillUri[..^"SKILL.md".Length];

        List<McpListedSkillResourceEntry> resources = [];

        foreach (McpListedSkillResourceEntry? resource in entry.Resources)
        {
            // Reject null entries, e.g. "resources": [null], which deserialization can accept.
            if (resource is null)
            {
                throw new JsonException($"Skill '{skillUri}' contains a null manifest entry.");
            }

            // Resources must stay under the skill root, e.g. skill://unit-converter/references/rates.md.
            if (!resource.Uri.StartsWith(skillRootUri, StringComparison.Ordinal) ||
                resource.Uri.Length == skillRootUri.Length ||
                !AgentMcpListedSkill.IsResourceNameSafe(resource.Uri[skillRootUri.Length..]))
            {
                throw new JsonException($"Skill '{skillUri}' contains an invalid resource manifest entry.");
            }

            // The server also supplies SKILL.md as a resource. Skip it here because we read it separately
            // as skill instructions and do not include it in the list of supporting resources.
            if (string.Equals(resource.Uri, skillUri, StringComparison.Ordinal))
            {
                continue;
            }

            resources.Add(resource);
        }

        return resources;
    }
}
