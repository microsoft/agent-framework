// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A file-path-backed skill script. Represents a script file on disk that requires an external runner to run.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentFileSkillScript : AgentSkillScript
{
    /// <summary>
    /// Cached JSON schema element describing the expected argument format: a string array of CLI arguments.
    /// </summary>
    private static readonly JsonElement s_defaultSchema = CreateDefaultSchema();

    private readonly AgentFileSkillScriptRunner? _runner;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillScript"/> class.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="fullPath">The absolute file path to the script.</param>
    /// <param name="runner">Optional external runner for running the script. An <see cref="InvalidOperationException"/> is thrown from <see cref="RunAsync"/> if no runner is provided.</param>
    internal AgentFileSkillScript(string name, string fullPath, AgentFileSkillScriptRunner? runner = null)
        : base(name)
    {
        this.FullPath = Throw.IfNullOrWhitespace(fullPath);
        this._runner = runner;
    }

    /// <summary>
    /// Gets the absolute file path to the script.
    /// </summary>
    public string FullPath { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Returns a fixed schema describing a string array of CLI arguments:
    /// <c>{"type":"array","items":{"type":"string"}}</c>.
    /// </remarks>
    public override JsonElement? ParametersSchema => s_defaultSchema;

    /// <inheritdoc/>
    public override async Task<object?> RunAsync(AgentSkill skill, JsonElement? arguments, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default)
    {
        if (skill is not AgentFileSkill fileSkill)
        {
            throw new InvalidOperationException($"File-based script '{this.Name}' requires an {nameof(AgentFileSkill)} but received '{skill.GetType().Name}'.");
        }

        if (this._runner is null)
        {
            throw new InvalidOperationException(
                $"Script '{this.Name}' cannot be executed because no {nameof(AgentFileSkillScriptRunner)} was provided. " +
                $"Supply a script runner when constructing {nameof(AgentFileSkillsSource)} to enable script execution.");
        }

        return await this._runner(fileSkill, this, arguments, serviceProvider, cancellationToken).ConfigureAwait(false);
    }

    private static JsonElement CreateDefaultSchema()
    {
        using JsonDocument document = JsonDocument.Parse("""{"type":"array","items":{"type":"string"}}""");
        return document.RootElement.Clone();
    }
}
