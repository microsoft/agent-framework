// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess;

internal sealed class MessageDelivery(MessageEnvelope message, Func<MessageEnvelope, CancellationToken, ValueTask> servicer, Task<object?> resultTask)
{
    public MessageEnvelope Message { get; } = message;
    public Func<MessageEnvelope, CancellationToken, ValueTask> Servicer { get; } = servicer;
    public Task<object?> ResultTask { get; } = resultTask;

    public ValueTask InvokeAsync(CancellationToken cancellation) => this.Servicer(this.Message, cancellation);
}
