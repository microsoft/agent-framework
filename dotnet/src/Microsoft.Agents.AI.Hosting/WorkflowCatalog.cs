// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// todo
/// </summary>
public abstract class WorkflowCatalog
{
    /// <summary>
    /// todo
    /// </summary>
    protected WorkflowCatalog()
    {
    }

    /// <summary>
    /// todo
    /// </summary>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    public abstract IAsyncEnumerable<Workflow> GetWorkflowsAsync(CancellationToken cancellationToken = default);
}
