// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Fluent builder for constructing an <see cref="AgentSkillsProvider"/> backed by one or more skill sources.
/// </summary>
/// <remarks>
/// <code>
/// var provider = new AgentSkillsProviderBuilder()
///     .UseFileSkills("/path/to/skills")
///     .Build();
/// </code>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillsProviderBuilder
{
    private readonly List<Func<AgentFileSkillScriptExecutor?, ILoggerFactory?, AgentSkillsSource>> _sourceFactories = [];
    private AgentSkillsProviderOptions? _options;
    private ILoggerFactory? _loggerFactory;
    private AgentFileSkillScriptExecutor? _scriptExecutor;
    private Func<AgentSkill, bool>? _filter;
    private bool _cacheSkills = true;

    /// <summary>
    /// Adds a file-based skill source that discovers skills from a filesystem directory.
    /// </summary>
    /// <remarks>
    /// The script executor is resolved using the following fallback order:
    /// <list type="number">
    /// <item><description>The <paramref name="scriptExecutor"/> passed to this method, if provided.</description></item>
    /// <item><description>The builder-level executor set via <see cref="UseFileScriptExecutor"/>.</description></item>
    /// </list>
    /// If neither is available, <see cref="Build"/> throws <see cref="InvalidOperationException"/>.
    /// </remarks>
    /// <param name="skillPath">Path to search for skills.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="scriptExecutor">
    /// Optional executor for file-based scripts. When provided, overrides the builder-level executor
    /// set via <see cref="UseFileScriptExecutor"/> for this source.
    /// </param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileSkill(string skillPath, AgentFileSkillsSourceOptions? options = null, AgentFileSkillScriptExecutor? scriptExecutor = null)
    {
        return this.UseFileSkills([skillPath], options, scriptExecutor);
    }

    /// <summary>
    /// Adds a file-based skill source that discovers skills from multiple filesystem directories.
    /// </summary>
    /// <remarks>
    /// The script executor is resolved using the following fallback order:
    /// <list type="number">
    /// <item><description>The <paramref name="scriptExecutor"/> passed to this method, if provided.</description></item>
    /// <item><description>The builder-level executor set via <see cref="UseFileScriptExecutor"/>.</description></item>
    /// </list>
    /// If neither is available, <see cref="Build"/> throws <see cref="InvalidOperationException"/>.
    /// </remarks>
    /// <param name="skillPaths">Paths to search for skills.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="scriptExecutor">
    /// Optional executor for file-based scripts. When provided, overrides the builder-level executor
    /// set via <see cref="UseFileScriptExecutor"/> for this source.
    /// </param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileSkills(IEnumerable<string> skillPaths, AgentFileSkillsSourceOptions? options = null, AgentFileSkillScriptExecutor? scriptExecutor = null)
    {
        this._sourceFactories.Add((builderScriptExecutor, loggerFactory) =>
        {
            var resolvedExecutor = scriptExecutor
                ?? builderScriptExecutor
                ?? throw new InvalidOperationException($"File-based skill sources require a script executor. Call {nameof(this.UseFileScriptExecutor)} or pass an executor to {nameof(this.UseFileSkill)}/{nameof(this.UseFileSkills)}.");
            return new AgentFileSkillsSource(skillPaths, resolvedExecutor, options, loggerFactory);
        });
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
    /// <param name="promptTemplate">The prompt template with <c>{skills}</c> placeholder for the skills list
    /// and <c>{runner_instructions}</c> for optional script runner instructions.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UsePromptTemplate(string promptTemplate)
    {
        this.EnsureOptions().SkillsInstructionPrompt = promptTemplate;
        return this;
    }

    /// <summary>
    /// Enables or disables the script approval gate.
    /// </summary>
    /// <param name="enabled">Whether script execution requires approval.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseScriptApproval(bool enabled = true)
    {
        this.EnsureOptions().ScriptApproval = enabled;
        return this;
    }

    /// <summary>
    /// Sets the executor for file-based skill scripts.
    /// </summary>
    /// <param name="executor">The delegate that executes file-based scripts.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseFileScriptExecutor(AgentFileSkillScriptExecutor executor)
    {
        this._scriptExecutor = Throw.IfNull(executor);
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
    /// Enables or disables skill caching after the first load.
    /// </summary>
    /// <param name="enabled"><see langword="true"/> to cache skills (default); <see langword="false"/> to reload from sources on every call.</param>
    /// <returns>This builder instance for chaining.</returns>
    public AgentSkillsProviderBuilder UseCache(bool enabled = true)
    {
        this._cacheSkills = enabled;
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
        configure(this.EnsureOptions());
        return this;
    }

    /// <summary>
    /// Builds the <see cref="AgentSkillsProvider"/>.
    /// </summary>
    /// <returns>A configured <see cref="AgentSkillsProvider"/>.</returns>
    public AgentSkillsProvider Build()
    {
        if (this._sourceFactories.Count == 0)
        {
            throw new InvalidOperationException("At least one skill source must be configured.");
        }

        var resolvedSources = new List<AgentSkillsSource>(this._sourceFactories.Count);
        foreach (var factory in this._sourceFactories)
        {
            resolvedSources.Add(factory(this._scriptExecutor, this._loggerFactory));
        }

        AgentSkillsSource source;
        if (resolvedSources.Count == 1)
        {
            source = resolvedSources[0];
        }
        else
        {
            source = new AggregateAgentSkillsSource(resolvedSources);
        }

        // Apply user-specified filter, then dedup, then optionally cache.
        if (this._filter != null)
        {
            source = new FilteringAgentSkillsSource(source, this._filter, this._loggerFactory);
        }

        // Wrap with dedup (first) then caching so duplicates are resolved before the result is cached.
        source = new DeduplicatingAgentSkillsSource(source, this._loggerFactory);

        if (this._cacheSkills)
        {
            source = new CachingAgentSkillsSource(source);
        }

        return new AgentSkillsProvider(source, this._options, this._loggerFactory);
    }

    private AgentSkillsProviderOptions EnsureOptions()
    {
        if (this._options == null)
        {
            this._options = new AgentSkillsProviderOptions();
        }

        return this._options;
    }
}
