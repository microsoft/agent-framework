// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for skill resources. A resource provides supplementary content (references, assets) to a skill.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSkillResource
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillResource"/> class.
    /// </summary>
    /// <param name="name">The resource name (e.g., relative path or identifier).</param>
    /// <param name="description">An optional description of the resource.</param>
    protected AgentSkillResource(string name, string? description = null)
    {
        this.Name = Throw.IfNullOrWhitespace(name);
        this.Description = description;
    }

    /// <summary>
    /// Gets the resource name.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Gets the optional resource description.
    /// </summary>
    public string? Description { get; }

    /// <summary>
    /// Reads the resource content asynchronously.
    /// </summary>
    /// <param name="serviceProvider">Optional service provider for dependency injection.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The resource content.</returns>
    public abstract Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default);
}
