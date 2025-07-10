// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess;

internal sealed class MessageEnvelope(object message, string? messageId = null, CancellationToken cancellation = default)
{
    public object Message { get; } = message;
    public string MessageId { get; } = messageId ?? Guid.NewGuid().ToString();
    public TopicId? Topic { get; private set; }
    public ActorId? Sender { get; private set; }
    public ActorId? Receiver { get; private set; }
    public CancellationToken Cancellation { get; } = cancellation;

    public MessageEnvelope WithSender(ActorId? sender)
    {
        this.Sender = sender;
        return this;
    }

    public MessageDelivery ForSend(ActorId receiver, Func<MessageEnvelope, CancellationToken, ValueTask<object?>> servicer)
    {
        this.Receiver = receiver;

        TaskCompletionSource<object?> tcs = new();
        return new MessageDelivery(this, async (MessageEnvelope envelope, CancellationToken cancellation) =>
        {
            try
            {
                object? result = await servicer(envelope, cancellation).ConfigureAwait(false);
                tcs.SetResult(result);
            }
            catch (OperationCanceledException exception)
            {
                tcs.TrySetCanceled(exception.CancellationToken);
            }
            catch (Exception exception)
            {
                tcs.SetException(exception);
            }
        }, tcs.Task);
    }

    public MessageDelivery ForPublish(TopicId topic, Func<MessageEnvelope, CancellationToken, ValueTask> servicer)
    {
        this.Topic = topic;

        TaskCompletionSource<object?> tcs = new();
        return new MessageDelivery(this, async (envelope, cancellation) =>
        {
            try
            {
                await servicer(envelope, cancellation).ConfigureAwait(false);
                tcs.SetResult(null);
            }
            catch (Exception ex)
            {
                tcs.SetException(ex);
            }
        }, tcs.Task);
    }
}
