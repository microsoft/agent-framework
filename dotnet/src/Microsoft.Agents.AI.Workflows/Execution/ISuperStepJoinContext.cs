// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface ISuperStepJoinContext
{
    bool WithCheckpointing { get; }
    bool ConcurrentRunsEnabled { get; }

    ValueTask ForwardWorkflowEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default);
    ValueTask SendMessageAsync<TMessage>(string senderId, [DisallowNull] TMessage message, CancellationToken cancellationToken = default);

    ValueTask<string> AttachSuperstepAsync(ISuperStepRunner superStepRunner, CancellationToken cancellationToken = default);
    ValueTask<bool> DetachSuperstepAsync(string id);
}
