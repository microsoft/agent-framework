// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Security;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
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
/// <para>
/// The provider can optionally own the lifetime of its underlying <see cref="AgentSkillsSource"/>. When
/// constructed via one of the convenience constructors (skill paths or in-memory skills) or via
/// <see cref="AgentSkillsProviderBuilder"/>, the source pipeline is created internally and owned by the
/// provider, so disposing the provider disposes the pipeline. When constructed from a caller-supplied
/// <see cref="AgentSkillsSource"/>, ownership is controlled by the <c>ownsSource</c> constructor
/// parameter and defaults to the caller retaining ownership.
/// </para>
/// </remarks>
public sealed partial class AgentSkillsProvider : AIContextProvider, IDisposable
{
    /// <summary>The name of the tool that loads a skill.</summary>
    public const string LoadSkillToolName = "load_skill";

    /// <summary>The name of the tool that reads a skill resource.</summary>
    public const string ReadSkillResourceToolName = "read_skill_resource";

    /// <summary>The name of the tool that runs a skill script.</summary>
    public const string RunSkillScriptToolName = "run_skill_script";

    /// <summary>The names of the tools that only read (never execute scripts from) the skills source.</summary>
    private static readonly HashSet<string> s_readOnlyToolNames = new(StringComparer.Ordinal)
    {
        LoadSkillToolName,
        ReadSkillResourceToolName,
    };

    /// <summary>The names of all tools exposed by this provider.</summary>
    private static readonly HashSet<string> s_allToolNames = new(StringComparer.Ordinal)
    {
        LoadSkillToolName,
        ReadSkillResourceToolName,
        RunSkillScriptToolName,
    };

    /// <summary>
    /// Gets an auto-approval rule that approves the read-only skill tools
    /// (<see cref="LoadSkillToolName"/> and <see cref="ReadSkillResourceToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// This rule only applies when approval is enabled for the matching tools in
    /// <see cref="AgentSkillsProviderOptions"/>. When the read-only skill tools require approval, add this rule to
    /// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve only the tools
    /// that read skill content, while still prompting for script execution
    /// (<see cref="RunSkillScriptToolName"/>) if it also requires approval.
    /// </para>
    /// <para>
    /// The rule matches on the tool name, returning <see langword="true"/> for read-only skill tools
    /// and <see langword="false"/> for all other tool calls so that subsequent rules continue to be evaluated.
    /// </para>
    /// </remarks>
    public static Func<FunctionCallContent, ValueTask<bool>> ReadOnlyToolsAutoApprovalRule { get; } =
        functionCall => new ValueTask<bool>(s_readOnlyToolNames.Contains(functionCall.Name));

    /// <summary>
    /// Gets an auto-approval rule that approves all skill tools, including the script execution tool
    /// (<see cref="RunSkillScriptToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// This rule only applies when approval is enabled for the matching tools in
    /// <see cref="AgentSkillsProviderOptions"/>. When skill tools require approval, add this rule to
    /// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve every skill
    /// tool that requires approval without prompting the user.
    /// </para>
    /// <para>
    /// The rule matches on the tool name, returning <see langword="true"/> for any skill tool
    /// and <see langword="false"/> for all other tool calls so that subsequent rules continue to be evaluated.
    /// </para>
    /// </remarks>
    public static Func<FunctionCallContent, ValueTask<bool>> AllToolsAutoApprovalRule { get; } =
        functionCall => new ValueTask<bool>(s_allToolNames.Contains(functionCall.Name));

    /// <summary>
    /// Placeholder token for the generated skills list in the prompt template.
    /// </summary>
    private const string SkillsPlaceholder = "{skills}";

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
        - Use `run_skill_script` to run referenced scripts, using the name exactly as listed.
        Only load what is needed, when it is needed.
        """;

    private readonly AgentSkillsSource _source;
    private readonly bool _ownsSource;
    private readonly AgentSkillsProviderOptions? _options;
    private readonly ILogger<AgentSkillsProvider> _logger;
    private bool _disposed;

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
                new CachingAgentSkillsSource(
                    new AgentFileSkillsSource(skillPaths, scriptRunner, fileOptions, loggerFactory)),
                loggerFactory),
            options,
            loggerFactory,
            ownsSource: true)
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
                new CachingAgentSkillsSource(
                    new AgentInMemorySkillsSource(Throw.IfNull(skills))),
                loggerFactory),
            options,
            loggerFactory,
            ownsSource: true)
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
    /// <param name="ownsSource">
    /// <see langword="true"/> to transfer ownership of <paramref name="source"/> to the provider so that it is
    /// disposed when the provider is disposed; <see langword="false"/> (the default) to leave ownership with the
    /// caller. Set this to <see langword="true"/> only when the provider is the sole owner of the source.
    /// </param>
    public AgentSkillsProvider(AgentSkillsSource source, AgentSkillsProviderOptions? options = null, ILoggerFactory? loggerFactory = null, bool ownsSource = false)
    {
        this._source = Throw.IfNull(source);
        this._ownsSource = ownsSource;
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
        var skills = await this._source.GetSkillsAsync(new AgentSkillsSourceContext(context.Agent, context.Session), cancellationToken).ConfigureAwait(false);
        if (skills is not { Count: > 0 })
        {
            return await base.ProvideAIContextAsync(context, cancellationToken).ConfigureAwait(false);
        }

        return new AIContext
        {
            Instructions = this.BuildSkillsInstructions(skills),
            Tools = this.BuildTools(skills),
        };
    }

    /// <summary>
    /// Releases the resources used by this provider. When the provider owns its underlying
    /// <see cref="AgentSkillsSource"/> (see the <c>ownsSource</c> constructor parameter), the source is
    /// disposed as well.
    /// </summary>
    public void Dispose()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;

        if (this._ownsSource)
        {
            this._source.Dispose();
        }
    }

    private IList<AIFunction> BuildTools(IList<AgentSkill> skills)
    {
        return
        [
            this.WrapWithApprovalIfRequired(AIFunctionFactory.Create(
                (string skillName, CancellationToken cancellationToken) => this.LoadSkillAsync(skills, skillName, cancellationToken),
                name: LoadSkillToolName,
                description: "Loads the full content of a specific skill"),
                this._options?.DisableLoadSkillApproval is not true),
            this.WrapWithApprovalIfRequired(AIFunctionFactory.Create(
                (string skillName, string resourceName, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default) =>
                    this.ReadSkillResourceAsync(skills, skillName, resourceName, serviceProvider, cancellationToken),
                name: ReadSkillResourceToolName,
                description: "Reads a resource associated with a skill, such as references, assets, or dynamic data."),
                this._options?.DisableReadSkillResourceApproval is not true),
            this.WrapWithApprovalIfRequired(AIFunctionFactory.Create(
                (string skillName, string scriptName, JsonElement? arguments = null, IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default) =>
                    this.RunSkillScriptAsync(skills, skillName, scriptName, arguments, serviceProvider, cancellationToken),
                name: RunSkillScriptToolName,
                description: "Runs a script associated with a skill."),
                this._options?.DisableRunSkillScriptApproval is not true),
        ];
    }

    private AIFunction WrapWithApprovalIfRequired(AIFunction function, bool requireApproval)
    {
        return requireApproval ? new ApprovalRequiredAIFunction(function) : function;
    }

    private string? BuildSkillsInstructions(IList<AgentSkill> skills)
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

        return new StringBuilder(promptTemplate)
            .Replace(SkillsPlaceholder, sb.ToString().TrimEnd())
            .ToString();
    }

    private async Task<string> LoadSkillAsync(IList<AgentSkill> skills, string skillName, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(skillName))
        {
            return "Error: Skill name cannot be empty.";
        }

        var skill = skills.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        LogSkillLoading(this._logger, skillName);

        return await skill.GetContentAsync(cancellationToken).ConfigureAwait(false);
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

        var skill = skills.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        try
        {
            var resource = await skill.GetResourceAsync(resourceName, cancellationToken).ConfigureAwait(false);
            if (resource is null)
            {
                return $"Error: Resource '{resourceName}' not found in skill '{skillName}'.";
            }

            return await resource.ReadAsync(serviceProvider, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogResourceReadError(this._logger, skillName, resourceName, ex);
            throw;
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

        var skill = skills.FirstOrDefault(skill => skill.Frontmatter.Name == skillName);
        if (skill == null)
        {
            return $"Error: Skill '{skillName}' not found.";
        }

        try
        {
            var script = await skill.GetScriptAsync(scriptName, cancellationToken).ConfigureAwait(false);
            if (script is null)
            {
                return $"Error: Script '{scriptName}' not found in skill '{skillName}'.";
            }

            return await script.RunAsync(skill, arguments, serviceProvider, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            LogScriptExecutionError(this._logger, skillName, scriptName, ex);

            if (this._options?.IncludeDetailedErrors == true)
            {
                return $"Error: Failed to execute script '{scriptName}' from skill '{skillName}'. Exception: {ex.Message}";
            }

            throw;
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
    }

    [LoggerMessage(LogLevel.Information, "Loading skill: {SkillName}")]
    private static partial void LogSkillLoading(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Error, "Failed to read resource '{ResourceName}' from skill '{SkillName}'")]
    private static partial void LogResourceReadError(ILogger logger, string skillName, string resourceName, Exception exception);

    [LoggerMessage(LogLevel.Error, "Failed to execute script '{ScriptName}' from skill '{SkillName}'")]
    private static partial void LogScriptExecutionError(ILogger logger, string skillName, string scriptName, Exception exception);
}
