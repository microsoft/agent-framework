// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

internal interface IWorkflowEventChain
{
    ValueTask<bool> RaiseAsync(WorkflowEvent evt, CancellationToken cancellationToken);
}
