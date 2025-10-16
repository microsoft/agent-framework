// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>
/// Provides an executor that batches received chat messages that it then releases when
/// receiving a <see cref="TurnToken"/>.
/// </summary>
internal sealed class CollectChatMessagesExecutor(string id) : ChatProtocolExecutor(id), IResettableExecutor
{
    /// <inheritdoc/>
    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => context.SendMessageAsync(messages, cancellationToken: cancellationToken);

    ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();
}
