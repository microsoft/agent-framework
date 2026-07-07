// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for skill sources. A skill source provides skills from a specific origin
/// (filesystem, remote server, database, in-memory, etc.).
/// </summary>
/// <remarks>
/// Sources are <see cref="IDisposable"/> so that pipelines built from decorators can release any
/// resources they own. The default <see cref="Dispose(bool)"/> implementation does nothing; sources
/// that hold disposable resources override it. Decorators dispose the source they wrap.
/// </remarks>
public abstract class AgentSkillsSource : IDisposable
{
    /// <summary>
    /// Gets the skills provided by this source.
    /// </summary>
    /// <param name="context">Contextual information about the agent and session requesting skills.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A collection of skills from this source.</returns>
    public abstract Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default);

    /// <summary>
    /// Releases all resources used by this source.
    /// </summary>
    public void Dispose()
    {
        this.Dispose(disposing: true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Releases the unmanaged resources used by this source and optionally releases the managed resources.
    /// </summary>
    /// <param name="disposing">
    /// <see langword="true"/> to release both managed and unmanaged resources;
    /// <see langword="false"/> to release only unmanaged resources.
    /// </param>
    /// <remarks>The default implementation does nothing. Override to release owned resources.</remarks>
    protected virtual void Dispose(bool disposing)
    {
    }
}
