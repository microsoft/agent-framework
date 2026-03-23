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
/// A file-path-backed skill script. Represents a script file on disk that requires an external executor to run.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentFileSkillScript : AgentSkillScript
{
    private readonly AgentFileSkillScriptExecutor _executor;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillScript"/> class.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="fullPath">The absolute file path to the script.</param>
    /// <param name="executor">External executor for running the script.</param>
    internal AgentFileSkillScript(string name, string fullPath, AgentFileSkillScriptExecutor executor)
        : base(name)
    {
        this.FullPath = Throw.IfNullOrWhitespace(fullPath);
        this._executor = Throw.IfNull(executor);
    }

    /// <summary>
    /// Gets the absolute file path to the script.
    /// </summary>
    public string FullPath { get; }

    /// <summary>
    /// Executes the file-based script using the configured external executor.
    /// </summary>
    /// <param name="skill">The skill that owns this script. Must be an <see cref="AgentFileSkill"/>.</param>
    /// <param name="arguments">Arguments for script execution.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The script execution result.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when <paramref name="skill"/> is not an <see cref="AgentFileSkill"/>.
    /// </exception>
    public override async Task<object?> ExecuteAsync(AgentSkill skill, AIFunctionArguments arguments, CancellationToken cancellationToken = default)
    {
        if (skill is not AgentFileSkill fileSkill)
        {
            throw new InvalidOperationException($"File-based script '{this.Name}' requires an {nameof(AgentFileSkill)} but received '{skill.GetType().Name}'.");
        }

        return await this._executor(fileSkill, this, arguments, cancellationToken).ConfigureAwait(false);
    }
}
