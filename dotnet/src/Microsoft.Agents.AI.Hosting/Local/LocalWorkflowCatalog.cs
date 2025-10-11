// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.Local;

internal sealed class LocalWorkflowCatalog : WorkflowCatalog
{
    public readonly HashSet<string> _registeredWorkflows;
    private readonly IServiceProvider _serviceProvider;

    public LocalWorkflowCatalog(LocalWorkflowRegistry workflowRegistry, IServiceProvider serviceProvider)
    {
        this._registeredWorkflows = [.. workflowRegistry.WorkflowNames];
        this._serviceProvider = serviceProvider;
    }

    public override async IAsyncEnumerable<Workflow> GetWorkflowsAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.CompletedTask.ConfigureAwait(false);

        foreach (var name in this._registeredWorkflows)
        {
            var workflow = this._serviceProvider.GetKeyedService<Workflow>(name);
            if (workflow is not null)
            {
                yield return workflow;
            }
        }
    }
}
