// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Runtime.InProcess;

internal sealed class MessageEnvelope
{
    public object Message { get; }
    public string MessageId { get; }
    public TopicId? Topic { get; private set; }
    public AgentId? Sender { get; private set; }
    public AgentId? Receiver { get; private set; }
    public CancellationToken Cancellation { get; }

    public MessageEnvelope(object message, string? messageId = null, CancellationToken cancellation = default)
    {
        this.Message = message;
        this.MessageId = messageId ?? Guid.NewGuid().ToString();
        this.Cancellation = cancellation;
    }

    public MessageEnvelope WithSender(AgentId? sender)
    {
        this.Sender = sender;
        return this;
    }

    public MessageDelivery ForSend(AgentId receiver, Func<MessageEnvelope, CancellationToken, ValueTask<object?>> servicer)
    {
        this.Receiver = receiver;

        ResultSink<object?> resultSink = new();

        return new MessageDelivery(this, BoundServicer, resultSink);

        async ValueTask BoundServicer(MessageEnvelope envelope, CancellationToken cancellation)
        {
            try
            {
                object? result = await servicer(envelope, cancellation).ConfigureAwait(false);
                resultSink.SetResult(result);
            }
            catch (OperationCanceledException exception)
            {
                resultSink.SetCancelled(exception);
            }
#pragma warning disable CA1031 // Do not catch general exception types
            catch (Exception exception)
#pragma warning restore CA1031 // Do not catch general exception types
            {
                resultSink.SetException(exception);
            }
        }
    }

    public MessageDelivery ForPublish(TopicId topic, Func<MessageEnvelope, CancellationToken, ValueTask> servicer)
    {
        this.Topic = topic;

        ResultSink<object?> waitForPublish = new();

        async ValueTask BoundServicer(MessageEnvelope envelope, CancellationToken cancellation)
        {
            try
            {
                await servicer(envelope, cancellation).ConfigureAwait(false);
                waitForPublish.SetResult(null);
            }
#pragma warning disable CA1031 // Do not catch general exception types
            catch (Exception exception)
#pragma warning restore CA1031 // Do not catch general exception types
            {
                waitForPublish.SetException(exception);
            }
        }

        return new MessageDelivery(this, BoundServicer, waitForPublish);
    }
}
