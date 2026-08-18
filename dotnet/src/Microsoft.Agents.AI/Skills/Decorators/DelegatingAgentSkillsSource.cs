// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for skill sources that delegate operations to an inner source
/// while allowing for extensibility and customization.
/// </summary>
/// <remarks>
/// <see cref="DelegatingAgentSkillsSource"/> implements the decorator pattern for <see cref="AgentSkillsSource"/>,
/// enabling the creation of source pipelines where each layer can add functionality (caching, deduplication,
/// filtering, etc.) while delegating core operations to an underlying source.
/// </remarks>
public abstract class DelegatingAgentSkillsSource : AgentSkillsSource
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAgentSkillsSource"/> class with the specified inner source.
    /// </summary>
    /// <param name="innerSource">The underlying skill source that will handle the core operations.</param>
    protected DelegatingAgentSkillsSource(AgentSkillsSource innerSource)
    {
        this.InnerSource = Throw.IfNull(innerSource);
    }

    /// <summary>
    /// Gets the inner skill source that receives delegated operations.
    /// </summary>
    protected AgentSkillsSource InnerSource { get; }

    /// <inheritdoc/>
    public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        => this.InnerSource.GetSkillsAsync(context, cancellationToken);

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this.InnerSource.Dispose();
        }

        base.Dispose(disposing);
    }
}
