// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Security;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that exposes agent skills from one or more <see cref="AgentSkillsSource"/> instances.
/// </summary>
/// <remarks>
/// <para>
/// This provider implements the progressive disclosure pattern from the
/// <see href="https://agentskills.io/">Agent Skills specification</see>:
/// </para>
/// <list type="number">
/// <item><description><strong>Advertise</strong> — skill names and descriptions are injected into the system prompt.</description></item>
/// <item><description><strong>Load</strong> — the full skill body is returned via the <c>load_skill</c> tool.</description></item>
/// <item><description><strong>Read resources</strong> — supplementary content is read on demand via the <c>read_skill_resource</c> tool.</description></item>
/// <item><description><strong>Run scripts</strong> — scripts are executed via the <c>run_skill_script</c> tool (when scripts exist).</description></item>
/// </list>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed partial class AgentSkillsProvider : AIContextProvider
{
    /// <summary>
    /// Placeholder token for the generated skills list in the prompt template.
    /// </summary>
    private const string SkillsPlaceholder = "{skills}";

    /// <summary>
    /// Placeholder token for the script instructions in the prompt template.
    /// </summary>
    private const string ScriptInstructionsPlaceholder = "{script_instructions}";

    /// <summary>
    /// Placeholder token for the resource instructions in the prompt template.
    /// </summary>
    private const string ResourceInstructionsPlaceholder = "{resource_instructions}";

    private const string DefaultSkillsInstructionPrompt =
        """
        You have access to skills containing domain-specific knowledge and capabilities.
        Each skill provides specialized instructions, reference documents, and assets for specific tasks.

        <available_skills>
        {skills}
        </available_skills>

        When a task aligns with a skill's domain, follow these steps in exact order:
        - Use `load_skill` to retrieve the skill's instructions.
        - Follow the provided guidance.
        {resource_instructions}
        {script_instructions}
        Only load what is needed, when it is needed.
        """;

    private readonly AgentSkillsSource _source;
    private readonly AgentSkillsProviderOptions? _options;
    private readonly ILogger<AgentSkillsProvider> _logger;
    private Task<AIContext>? _contextTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class
    /// that discovers file-based skills from a single directory.
    /// Duplicate skill names are automatically deduplicated (first occurrence wins).
    /// </summary>
    /// <param name="skillPath">Path to search for skills.</param>
    /// <param name="scriptRunner">Optional delegate that runs file-based scripts. Required only when skills contain scripts.</param>
    /// <param name="fileOptions">Optional options that control skill discovery behavior.</param>
    /// <param name="options">Optional provider configuration.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentSkillsProvider(
        string skillPath,
        AgentFileSkillScriptRunner? scriptRunner = null,
        AgentFileSkillsSourceOptions? fileOptions = null,
        AgentSkillsProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this([Throw.IfNull(skillPath)], scriptRunner, fileOptions, options, loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class
    /// that discovers file-based skills from multiple directories.
    /// Duplicate skill names are automatically deduplicated (first occurrence wins).
    /// </summary>
    /// <param name="skillPaths">Paths to search for skills.</param>
    /// <param name="scriptRunner">Optional delegate that runs file-based scripts. Required only when skills contain scripts.</param>
    /// <param name="fileOptions">Optional options that control skill discovery behavior.</param>
    /// <param name="options">Optional provider configuration.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentSkillsProvider(
        IEnumerable<string> skillPaths,
        AgentFileSkillScriptRunner? scriptRunner = null,
        AgentFileSkillsSourceOptions? fileOptions = null,
        AgentSkillsProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this(
            new DeduplicatingAgentSkillsSource(
                new AgentFileSkillsSource(skillPaths, scriptRunner, fileOptions, loggerFactory),
                loggerFactory),
            options,
            loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class.
    /// Duplicate skill names are automatically deduplicated (first occurrence wins).
    /// </summary>
    /// <param name="skills">The skills to include.</param>
    public AgentSkillsProvider(params AgentSkill[] skills)
        : this(skills as IEnumerable<AgentSkill>)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class.
    /// Duplicate skill names are automatically deduplicated (first occurrence wins).
    /// </summary>
    /// <param name="skills">The skills to include.</param>
    /// <param name="options">Optional provider configuration.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentSkillsProvider(
        IEnumerable<AgentSkill> skills,
        AgentSkillsProviderOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this(
            new DeduplicatingAgentSkillsSource(
                new AgentInMemorySkillsSource(Throw.IfNull(skills)),
                loggerFactory),
            options,
            loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class
    /// from a custom <see cref="AgentSkillsSource"/>. Unlike other constructors, this one does not
    /// apply automatic deduplication, allowing callers to customize deduplication behavior via the source pipeline.
    /// </summary>
    /// <param name="source">The skill source providing skills.</param>
    /// <param name="options">Optional configuration.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentSkillsProvider(AgentSkillsSource source, AgentSkillsProviderOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        this._source = Throw.IfNull(source);
        this._options = options;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<AgentSkillsProvider>();

        if (options?.SkillsInstructionPrompt is string prompt)
        {
            ValidatePromptTemplate(prompt, nameof(options));
        }
    }

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        if (this._options?.DisableCaching == true)
        {
            return await this.CreateContextAsync(context, cancellationToken).ConfigureAwait(false);
        }

        return await this.GetOrCreateContextAsync(context, cancellationToken).ConfigureAwait(false);
    }

    private async Task<AIContext> CreateContextAsync(InvokingContext context, CancellationToken cancellationToken)
    {
        var skills = await this._source.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
        if (skills is not { Count: > 0 })
        {
            return await base.ProvideAIContextAsync(context, cancellationToken).ConfigureAwait(false);
        }

        bool hasScripts = skills.Any(s => s.Scripts is { Count: > 0 });
        bool hasResources = skills.Any(s => s.Resources is { Count: > 0 });

        return new AIContext
        {
            Instructions = this.BuildSkillsInstructions(skills, includeScriptInstructions: hasScripts, hasResources),
            Tools = this.BuildTools(skills, hasScripts, hasResources),
        };
    }

    private async Task<AIContext> GetOrCreateContextAsync(InvokingContext context, CancellationToken cancellationToken)
    {
        var tcs = new TaskCompletionSource<AIContext>(TaskCreationOptions.RunContinuationsAsynchronously);

        if (Interlocked.CompareExchange(ref this._contextTask, tcs.Task, null) is { } existing)
        {
            return await existing.ConfigureAwait(false);
        }

        try
        {
            var result = await this.CreateContextAsync(context, cancellationToken).ConfigureAwait(false);
            tcs.SetResult(result);
            return result;
        }
        catch (Exception ex)
        {
            this._contextTask = null;
            tcs.TrySetException(ex);
            throw;
        }
    }

    private IList<AIFunction> BuildTools(IList<AgentSkill> skills, bool hasScripts, bool hasResources)
    {
        IList<AIFunction> tools =
        [
            AIFunctionFactory.Create(
                (string skillName) => this.LoadSkill(skills, skillName),
                name: "load_skill",
                description: "Loads the full content of a specific skill"),
        ];

        if (hasResources)
        {
            tools.Add(AIFunctionFactory.Create(
                (string skillName, string resourceName, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default) =>
                    this.ReadSkillResourceAsync(skills, skillName, resourceName, serviceProvider, cancellationToken),
                name: "read_skill_resource",
                description: "Reads a resource associated with a skill, such as references, assets, or dynamic data."));
        }

        if (!hasScripts)
        {
            return tools;
        }

        AIFunction scriptFunction = AIFunctionFactory.Create(
            (string skillName, string scriptName, JsonElement? arguments = null, IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default) =>
                this.RunSkillScriptAsync(skills, skillName, scriptName, arguments, serviceProvider, cancellationToken),
            name: "run_skill_script",
            description: "Runs a script associated with a skill.");

        if (this._options?.ScriptApproval == true)
        {
            return [.. tools, new ApprovalRequiredAIFunction(scriptFunction)];
        }

        return [.. tools, scriptFunction];
    }

    private string? BuildSkillsInstructions(IList<AgentSkill> skills, bool includeScriptInstructions, bool includeResourceInstructions)
    {
        string promptTemplate = this._options?.SkillsInstructionPrompt ?? DefaultSkillsInstructionPrompt;

        var sb = new StringBuilder();
        foreach (var skill in skills.OrderBy(s => s.Frontmatter.Name, StringComparer.Ordinal))
        {
            sb.AppendLine("  <skill>");
            sb.AppendLine($"    <name>{SecurityElement.Escape(skill.Frontmatter.Name)}</name>");
            sb.AppendLine($"    <description>{SecurityElement.Escape(skill.Frontmatter.Description)}</description>");
            sb.AppendLine("  </skill>");
        }

        string resourceInstruction = includeResourceInstructions
            ? """
            - Use `read_skill_resource` to read any referenced resources, using the name exactly as listed
               (e.g. `"style-guide"` not `"style-guide.md"`, `"references/FAQ.md"` not `"FAQ.md"`).
            """
            : string.Empty;

        string scriptInstruction = includeScriptInstructions
            ? "- Use `run_skill_script` to run referenced scripts, using the name exactly as listed."
            : string.Empty;

        return new StringBuilder(promptTemplate)
            .Replace(SkillsPlaceholder, sb.ToString().TrimEnd())
            .Replace(ResourceInstructionsPlaceholder, resourceInstruction)
            .Replace(ScriptInstructionsPlaceholder, scriptInstruction)
            .ToString();
    }

    private string LoadSkill(IList<AgentSkill> skills, string skillName)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        var skill = skills?.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        LogSkillLoading(this._logger, skillName);

        return skill.Content;
    }

    private async Task<object?> ReadSkillResourceAsync(IList<AgentSkill> skills, string skillName, string resourceName, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        if (string.IsNullOrWhiteSpace(resourceName))
        {
            return "Error: Resource name cannot be empty.";
        }

        var skill = skills?.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        var resource = skill.Resources?.FirstOrDefault(resource => resource.Name == resourceName);
        if (resource is null)
        {
            return $"Error: Resource '{resourceName}' not found in skill '{skillName}'.";
        }

        try
        {
            return await resource.ReadAsync(serviceProvider, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogResourceReadError(this._logger, skillName, resourceName, ex);
            return $"Error: Failed to read resource '{resourceName}' from skill '{skillName}'.";
        }
    }

    private async Task<object?> RunSkillScriptAsync(IList<AgentSkill> skills, string skillName, string scriptName, JsonElement? arguments = null, IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        if (string.IsNullOrWhiteSpace(scriptName))
        {
            return "Error: Script name cannot be empty.";
        }

        var skill = skills?.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        var script = skill.Scripts?.FirstOrDefault(resource => resource.Name == scriptName);
        if (script is null)
        {
            return $"Error: Script '{scriptName}' not found in skill '{skillName}'.";
        }

        try
        {
            return await script.RunAsync(skill, arguments, serviceProvider, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogScriptExecutionError(this._logger, skillName, scriptName, ex);
            return $"Error: Failed to execute script '{scriptName}' from skill '{skillName}'.";
        }
    }

    /// <summary>
    /// Validates that a custom prompt template contains the required placeholder tokens.
    /// </summary>
    private static void ValidatePromptTemplate(string template, string paramName)
    {
        if (template.IndexOf(SkillsPlaceholder, StringComparison.Ordinal) < 0)
        {
            throw new ArgumentException(
                $"The custom prompt template must contain the '{SkillsPlaceholder}' placeholder for the generated skills list.",
                paramName);
        }

        if (template.IndexOf(ResourceInstructionsPlaceholder, StringComparison.Ordinal) < 0)
        {
            throw new ArgumentException(
                $"The custom prompt template must contain the '{ResourceInstructionsPlaceholder}' placeholder for resource instructions.",
                paramName);
        }

        if (template.IndexOf(ScriptInstructionsPlaceholder, StringComparison.Ordinal) < 0)
        {
            throw new ArgumentException(
                $"The custom prompt template must contain the '{ScriptInstructionsPlaceholder}' placeholder for script instructions.",
                paramName);
        }
    }

    [LoggerMessage(LogLevel.Information, "Loading skill: {SkillName}")]
    private static partial void LogSkillLoading(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Error, "Failed to read resource '{ResourceName}' from skill '{SkillName}'")]
    private static partial void LogResourceReadError(ILogger logger, string skillName, string resourceName, Exception exception);

    [LoggerMessage(LogLevel.Error, "Failed to execute script '{ScriptName}' from skill '{SkillName}'")]
    private static partial void LogScriptExecutionError(ILogger logger, string skillName, string scriptName, Exception exception);
}
