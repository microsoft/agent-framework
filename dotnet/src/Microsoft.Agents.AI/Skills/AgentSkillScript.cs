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
/// Abstract base class for skill scripts. A script represents an executable action associated with a skill.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSkillScript
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillScript"/> class.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="description">An optional description of the script.</param>
    protected AgentSkillScript(string name, string? description = null)
    {
        this.Name = Throw.IfNullOrWhitespace(name);
        this.Description = description;
    }

    /// <summary>
    /// Gets the script name.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Gets the optional script description.
    /// </summary>
    public string? Description { get; }

    /// <summary>
    /// Gets the JSON schema describing the parameters accepted by this script, or <see langword="null"/> if not available.
    /// </summary>
    public virtual JsonElement? ParametersSchema => null;

    /// <summary>
    /// Runs the script with the given arguments.
    /// </summary>
    /// <param name="skill">The skill that owns this script.</param>
    /// <param name="arguments">Raw JSON arguments for script execution, preserving the original format (object or array) sent by the caller.</param>
    /// <param name="serviceProvider">Optional service provider for dependency injection.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The script execution result.</returns>
    public abstract Task<object?> RunAsync(AgentSkill skill, JsonElement? arguments, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default);
}
