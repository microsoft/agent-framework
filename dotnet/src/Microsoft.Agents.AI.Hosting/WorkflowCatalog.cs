// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a catalog of registered workflows within the hosting environment.
/// </summary>
public abstract class WorkflowCatalog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowCatalog"/> class.
    /// </summary>
    protected WorkflowCatalog()
    {
    }

    /// <summary>
    /// Asynchronously retrieves all registered workflows from the catalog.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public abstract IAsyncEnumerable<Workflow> GetWorkflowsAsync(CancellationToken cancellationToken = default);
}
