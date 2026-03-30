// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A file-path-backed skill script. Represents a script file on disk that requires an external runner to run.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentFileSkillScript : AgentSkillScript
{
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
    public override async Task<object?> RunAsync(AgentSkill skill, AIFunctionArguments arguments, CancellationToken cancellationToken = default)
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

        return await this._runner(fileSkill, this, arguments, cancellationToken).ConfigureAwait(false);
    }
}
