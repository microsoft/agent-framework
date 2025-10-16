// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

public static partial class AgentWorkflowBuilder
{
    /// <summary>
    /// Provides an executor that batches received chat messages that it then publishes as the final result
    /// when receiving a <see cref="TurnToken"/>.
    /// </summary>
    internal sealed class OutputMessagesExecutor() : ChatProtocolExecutor("OutputMessages"), IResettableExecutor
    {
        protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync(messages, cancellationToken);

        ValueTask IResettableExecutor.ResetAsync() => default;
    }
}
