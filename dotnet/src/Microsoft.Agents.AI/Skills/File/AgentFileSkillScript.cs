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
    private readonly AgentFileSkillScriptRunner _runner;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillScript"/> class.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="fullPath">The absolute file path to the script.</param>
    /// <param name="runner">External runner for running the script.</param>
    internal AgentFileSkillScript(string name, string fullPath, AgentFileSkillScriptRunner runner)
        : base(name)
    {
        this.FullPath = Throw.IfNullOrWhitespace(fullPath);
        this._runner = Throw.IfNull(runner);
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

        return await this._runner(fileSkill, this, arguments, cancellationToken).ConfigureAwait(false);
    }
}
