// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface ISuperStepJoinContext
{
    bool WithCheckpointing { get; }

    ValueTask ForwardWorkflowEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellation = default);
    ValueTask SendMessageAsync<TMessage>(string senderId, [DisallowNull] TMessage message, CancellationToken cancellation = default);

    ValueTask AttachSuperstepAsync(ISuperStepRunner superStepRunner, CancellationToken cancellation = default);
}
