// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Security;
using System.Text;
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
/// <see href="https://agentskills.io/specification">Agent Skills specification</see>:
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
    /// Placeholder token for the runner/script instructions in the prompt template.
    /// </summary>
    private const string RunnerInstructionsPlaceholder = "{runner_instructions}";

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
        - Use `read_skill_resource` to read any referenced resources, using the name exactly as listed
           (e.g. `"style-guide"` not `"style-guide.md"`, `"references/FAQ.md"` not `"FAQ.md"`).
        {runner_instructions}
        Only load what is needed, when it is needed.
        """;

    private readonly AgentSkillsSource _source;
    private readonly AgentSkillsProviderOptions? _options;
    private readonly ILogger<AgentSkillsProvider> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillsProvider"/> class.
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
        var skills = await this._source.GetSkillsAsync(cancellationToken).ConfigureAwait(false);
        if (skills is not { Count: > 0 })
        {
            return await base.ProvideAIContextAsync(context, cancellationToken).ConfigureAwait(false);
        }

        bool hasScripts = skills.Any(s => s.Scripts is { Count: > 0 });

        return new AIContext
        {
            Instructions = this.BuildSkillsInstructions(skills, includeScriptInstructions: hasScripts),
            Tools = this.BuildTools(skills, hasScripts),
        };
    }

    private IList<AIFunction> BuildTools(IList<AgentSkill> skills, bool hasScripts)
    {
        IList<AIFunction> tools =
        [
            AIFunctionFactory.Create(
                (string skillName) => this.LoadSkill(skills, skillName),
                name: "load_skill",
                description: "Loads the full content of a specific skill"),
            AIFunctionFactory.Create(
                (string skillName, string resourceName, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default) =>
                    this.ReadSkillResourceAsync(skills, skillName, resourceName, serviceProvider, cancellationToken),
                name: "read_skill_resource",
                description: "Reads a resource associated with a skill, such as references, assets, or dynamic data."),
        ];

        if (!hasScripts)
        {
            return tools;
        }

        AIFunction scriptFunction = AIFunctionFactory.Create(
            (string skillName, string scriptName, IDictionary<string, object?>? arguments = null, IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default) =>
                this.RunSkillScriptAsync(skills, skillName, scriptName, arguments, serviceProvider, cancellationToken),
            name: "run_skill_script",
            description: "Runs a script associated with a skill.");

        if (this._options?.ScriptApproval == true)
        {
            return [.. tools, new ApprovalRequiredAIFunction(scriptFunction)];
        }

        return [.. tools, scriptFunction];
    }

    private string? BuildSkillsInstructions(IList<AgentSkill> skills, bool includeScriptInstructions)
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

        string scriptInstruction = includeScriptInstructions
            ? "- Use `run_skill_script` to run referenced scripts, using the name exactly as listed."
            : string.Empty;

        return new StringBuilder(promptTemplate)
            .Replace(SkillsPlaceholder, sb.ToString().TrimEnd())
            .Replace(RunnerInstructionsPlaceholder, scriptInstruction)
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
            return await resource.ReadAsync(new AIFunctionArguments() { Services = serviceProvider }, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogResourceReadError(this._logger, skillName, resourceName, ex);
            return $"Error: Failed to read resource '{resourceName}' from skill '{skillName}'.";
        }
    }

    private async Task<object?> RunSkillScriptAsync(IList<AgentSkill> skills, string skillName, string scriptName, IDictionary<string, object?>? arguments = null, IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        if (string.IsNullOrWhiteSpace(scriptName))
        {
            return "Error: Script name cannot be empty.";
        }

        var skill = skills?.FirstOrDefault(skill => skill.Frontmatter.Name == skillName); if (skill == null)
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
            return await script.ExecuteAsync(skill, new AIFunctionArguments(arguments) { Services = serviceProvider }, cancellationToken).ConfigureAwait(false);
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

        if (template.IndexOf(RunnerInstructionsPlaceholder, StringComparison.Ordinal) < 0)
        {
            throw new ArgumentException(
                $"The custom prompt template must contain the '{RunnerInstructionsPlaceholder}' placeholder for script runner instructions.",
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
