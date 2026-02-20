// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Security;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that discovers and exposes Agent Skills from filesystem directories.
/// </summary>
/// <remarks>
/// <para>
/// This provider implements the progressive disclosure pattern from the
/// <see href="https://agentskills.io/">Agent Skills specification</see>:
/// </para>
/// <list type="number">
/// <item><description><strong>Advertise</strong> — skill names and descriptions are injected into the system prompt (~100 tokens per skill).</description></item>
/// <item><description><strong>Load</strong> — the full SKILL.md body is returned via the <c>load_skill</c> tool.</description></item>
/// <item><description><strong>Read resources</strong> — supplementary files are read from disk on demand via the <c>read_skill_resource</c> tool.</description></item>
/// </list>
/// <para>
/// Skills are discovered by searching the configured directories for <c>SKILL.md</c> files.
/// Referenced resources are validated at initialization; invalid skills are excluded and logged.
/// </para>
/// <para>
/// <strong>Security:</strong> this provider only reads static content. Skill metadata is XML-escaped
/// before prompt embedding, and resource reads are guarded against path traversal and symlink escape.
/// Only use skills from trusted sources.
/// </para>
/// </remarks>
public sealed partial class FileAgentSkillsProvider : AIContextProvider
{
    private const string DefaultSkillsInstructionPrompt =
        """
        You have access to skills containing domain-specific knowledge and capabilities.
        Each skill provides specialized instructions, reference documents, and assets for specific tasks.

        <available_skills>
        {0}
        </available_skills>

        When a task aligns with a skill's domain:
        1. Use `load_skill` to retrieve the skill's instructions
        2. Follow the provided guidance
        3. Use `read_skill_resource` to read any references or other files mentioned by the skill

        Only load what is needed, when it is needed.
        """;

    private readonly Dictionary<string, FileAgentSkill> _skills;
    private readonly ILogger<FileAgentSkillsProvider> _logger;
    private readonly FileAgentSkillLoader _loader;
    private readonly AITool[] _tools;
    private readonly string _skillsInstructionPrompt;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillsProvider"/> class that searches a single directory for skills.
    /// </summary>
    /// <param name="skillPath">Path to an individual skill folder (containing a SKILL.md file) or a parent folder with skill subdirectories.</param>
    /// <param name="options">Optional configuration for prompt customization.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public FileAgentSkillsProvider(string skillPath, FileAgentSkillsProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
        : this([skillPath], options, loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillsProvider"/> class that searches multiple directories for skills.
    /// </summary>
    /// <param name="skillPaths">Paths to search. Each can be an individual skill folder or a parent folder with skill subdirectories.</param>
    /// <param name="options">Optional configuration for prompt customization.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public FileAgentSkillsProvider(IEnumerable<string> skillPaths, FileAgentSkillsProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<FileAgentSkillsProvider>();

        this._loader = new FileAgentSkillLoader(this._logger);
        this._skills = this._loader.DiscoverAndLoadSkills(skillPaths);

        string promptTemplate = options?.SkillsInstructionPrompt ?? DefaultSkillsInstructionPrompt;
        this._skillsInstructionPrompt = this._skills.Count > 0
            ? string.Format(promptTemplate, this.BuildSkillsListPrompt())
            : string.Empty;

        this._tools =
        [
            AIFunctionFactory.Create(
                this.LoadSkill,
                name: "load_skill",
                description: "Loads the full instructions for a specific skill."),
            AIFunctionFactory.Create(
                this.ReadSkillResourceAsync,
                name: "read_skill_resource",
                description: "Reads a file associated with a skill, such as references or assets."),
        ];
    }

    /// <inheritdoc />
    protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var inputContext = context.AIContext;

        if (this._skills.Count == 0)
        {
            return new ValueTask<AIContext>(inputContext);
        }

        string fullPrompt = this._skillsInstructionPrompt;

        string? instructions = inputContext.Instructions is not null
            ? inputContext.Instructions + "\n" + fullPrompt
            : fullPrompt;

        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = instructions,
            Messages = inputContext.Messages,
            Tools = (inputContext.Tools ?? []).Concat(this._tools)
        });
    }

    private string LoadSkill(string skillName)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        if (!this._skills.TryGetValue(skillName, out FileAgentSkill? skill))
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        LogSkillLoading(this._logger, skillName);

        return skill.Body;
    }

    private async Task<string> ReadSkillResourceAsync(string skillName, string resourceName, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        if (string.IsNullOrWhiteSpace(resourceName))
        {
            return "Error: Resource name cannot be empty.";
        }

        if (!this._skills.TryGetValue(skillName, out FileAgentSkill? skill))
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        try
        {
            return await this._loader.ReadSkillResourceAsync(skill, resourceName, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogResourceReadError(this._logger, skillName, resourceName, ex);
            return $"Error: Failed to read resource '{resourceName}' from skill '{skillName}'.";
        }
    }

    private string BuildSkillsListPrompt()
    {
        var sb = new StringBuilder();
        foreach (var skill in this._skills.Values)
        {
            sb.AppendLine("  <skill>");
            sb.AppendLine($"    <name>{SecurityElement.Escape(skill.Frontmatter.Name)}</name>");
            sb.AppendLine($"    <description>{SecurityElement.Escape(skill.Frontmatter.Description)}</description>");
            sb.AppendLine("  </skill>");
        }
        return sb.ToString().TrimEnd();
    }

    [LoggerMessage(LogLevel.Information, "Loading skill: {SkillName}")]
    private static partial void LogSkillLoading(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Error, "Failed to read resource '{ResourceName}' from skill '{SkillName}'")]
    private static partial void LogResourceReadError(ILogger logger, string skillName, string resourceName, Exception exception);
}
