// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Fluent builder for constructing an <see cref="AgentSkillsProvider"/> backed by a composite source.
/// </summary>
/// <remarks>
/// <para>
/// Use this builder to combine multiple skill sources into a single provider:
/// </para>
/// <code>
/// var provider = new AgentSkillsProviderBuilder()
///     .UseFileSkills("/path/to/skills")
///     .UseSkills(myInlineSkill1, myInlineSkill2)
///     .Build();
/// </code>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillsProviderBuilder
{
    private readonly List<Func<AgentFileSkillScriptRunner?, ILoggerFactory?, AgentSkillsSource>> _sourceFactories = [];
    private AgentSkillsProviderOptions? _options;
    private ILoggerFactory? _loggerFactory;
    private AgentFileSkillScriptRunner? _scriptRunner;
    private Func<AgentSkill, bool>? _filter;

    /// <summary>
    /// Adds a file-based skill source that discovers skills from a filesystem directory.
    /// </summary>
    /// <param name="skillPath">Path to search for skills.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="scriptRunner">
    /// Optional runner for file-based scripts. When provided, overrides the builder-level runner
    /// set via <see cref="UseFileScriptRunner"/>.
    /// </param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileSkill(string skillPath, AgentFileSkillsSourceOptions? options = null, AgentFileSkillScriptRunner? scriptRunner = null)
    {
        return this.UseFileSkills([skillPath], options, scriptRunner);
    }

    /// <summary>
    /// Adds a file-based skill source that discovers skills from multiple filesystem directories.
    /// </summary>
    /// <param name="skillPaths">Paths to search for skills.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="scriptRunner">
    /// Optional runner for file-based scripts. When provided, overrides the builder-level runner
    /// set via <see cref="UseFileScriptRunner"/>.
    /// </param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileSkills(IEnumerable<string> skillPaths, AgentFileSkillsSourceOptions? options = null, AgentFileSkillScriptRunner? scriptRunner = null)
    {
        this._sourceFactories.Add((builderScriptRunner, loggerFactory) =>
        {
            var resolvedRunner = scriptRunner
                ?? builderScriptRunner
                ?? throw new InvalidOperationException($"File-based skill sources require a script runner. Call {nameof(this.UseFileScriptRunner)} or pass a runner to {nameof(this.UseFileSkill)}/{nameof(this.UseFileSkills)}.");
            return new AgentFileSkillsSource(skillPaths, resolvedRunner, options, loggerFactory);
        });
        return this;
    }

    /// <summary>
    /// Adds a single skill.
    /// </summary>
    /// <param name="skill">The skill to add.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseSkill(AgentSkill skill)
    {
        return this.UseSkills(skill);
    }

    /// <summary>
    /// Adds one or more skills.
    /// </summary>
    /// <param name="skills">The skills to add.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseSkills(params AgentSkill[] skills)
    {
        var source = new AgentInMemorySkillsSource(skills);
        this._sourceFactories.Add((_, _) => source);
        return this;
    }

    /// <summary>
    /// Adds skills from the specified collection.
    /// </summary>
    /// <param name="skills">The skills to add.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseSkills(IEnumerable<AgentSkill> skills)
    {
        var source = new AgentInMemorySkillsSource(skills);
        this._sourceFactories.Add((_, _) => source);
        return this;
    }

    /// <summary>
    /// Adds a custom skill source.
    /// </summary>
    /// <param name="source">The custom skill source.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseSource(AgentSkillsSource source)
    {
        _ = Throw.IfNull(source);
        this._sourceFactories.Add((_, _) => source);
        return this;
    }

    /// <summary>
    /// Sets a custom system prompt template.
    /// </summary>
    /// <param name="promptTemplate">The prompt template with <c>{skills}</c> placeholder for the skills list,
    /// <c>{resource_instructions}</c> for optional resource instructions,
    /// and <c>{script_instructions}</c> for optional script instructions.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UsePromptTemplate(string promptTemplate)
    {
        this.GetOrCreateOptions().SkillsInstructionPrompt = promptTemplate;
        return this;
    }

    /// <summary>
    /// Enables or disables the script approval gate.
    /// </summary>
    /// <param name="enabled">Whether script execution requires approval.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseScriptApproval(bool enabled = true)
    {
        this.GetOrCreateOptions().ScriptApproval = enabled;
        return this;
    }

    /// <summary>
    /// Sets the runner for file-based skill scripts.
    /// </summary>
    /// <param name="runner">The delegate that runs file-based scripts.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileScriptRunner(AgentFileSkillScriptRunner runner)
    {
        this._scriptRunner = Throw.IfNull(runner);
        return this;
    }

    /// <summary>
    /// Sets the logger factory.
    /// </summary>
    /// <param name="loggerFactory">The logger factory.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseLoggerFactory(ILoggerFactory loggerFactory)
    {
        this._loggerFactory = loggerFactory;
        return this;
    }

    /// <summary>
    /// Sets a filter predicate that controls which skills are included.
    /// </summary>
    /// <remarks>
    /// Skills for which the predicate returns <see langword="true"/> are kept;
    /// others are excluded. Only one filter is supported; calling this method
    /// again replaces any previously set filter.
    /// </remarks>
    /// <param name="predicate">A predicate that determines which skills to include.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFilter(Func<AgentSkill, bool> predicate)
    {
        _ = Throw.IfNull(predicate);
        this._filter = predicate;
        return this;
    }

    /// <summary>
    /// Configures the <see cref="AgentSkillsProviderOptions"/> using the provided delegate.
    /// </summary>
    /// <param name="configure">A delegate to configure the options.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseOptions(Action<AgentSkillsProviderOptions> configure)
    {
        _ = Throw.IfNull(configure);
        configure(this.GetOrCreateOptions());
        return this;
    }

    /// <summary>
    /// Builds the <see cref="AgentSkillsProvider"/>.
    /// </summary>
    /// <returns>A configured <see cref="AgentSkillsProvider"/>.</returns>
    public AgentSkillsProvider Build()
    {
        var resolvedSources = new List<AgentSkillsSource>(this._sourceFactories.Count);
        foreach (var factory in this._sourceFactories)
        {
            resolvedSources.Add(factory(this._scriptRunner, this._loggerFactory));
        }

        AgentSkillsSource source;
        if (resolvedSources.Count == 1)
        {
            source = resolvedSources[0];
        }
        else
        {
            source = new AggregatingAgentSkillsSource(resolvedSources);
        }

        // Apply user-specified filter, then dedup.
        if (this._filter != null)
        {
            source = new FilteringAgentSkillsSource(source, this._filter, this._loggerFactory);
        }

        source = new DeduplicatingAgentSkillsSource(source, this._loggerFactory);

        return new AgentSkillsProvider(source, this._options, this._loggerFactory);
    }

    private AgentSkillsProviderOptions GetOrCreateOptions()
    {
        return this._options ??= new AgentSkillsProviderOptions();
    }
}
