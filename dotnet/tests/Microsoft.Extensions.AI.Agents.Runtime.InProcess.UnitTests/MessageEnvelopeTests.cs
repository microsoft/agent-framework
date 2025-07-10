// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class MessageEnvelopeTests
{
    [Fact]
    public void ConstructAllParametersTest()
    {
        // Arrange
        object message = new { Content = "Test message" };
        const string MessageId = "testid";
        CancellationToken cancellation = new();

        // Act
        MessageEnvelope envelope = new(message, MessageId, cancellation);

        // Assert
        Assert.Same(message, envelope.Message);
        Assert.Equal(MessageId, envelope.MessageId);
        Assert.Equal(cancellation, envelope.Cancellation);
        Assert.Null(envelope.Sender);
        Assert.Null(envelope.Receiver);
        Assert.Null(envelope.Topic);
    }

    [Fact]
    public void ConstructOnlyRequiredParametersTest()
    {
        // Arrange & Act
        MessageEnvelope envelope = new("test");

        // Assert
        Assert.NotNull(envelope.MessageId);
        Assert.NotEmpty(envelope.MessageId);
        // Verify it's a valid GUID
        Assert.True(Guid.TryParse(envelope.MessageId, out _));
    }

    [Fact]
    public void WithSenderTest()
    {
        // Arrange
        MessageEnvelope envelope = new("test");
        ActorId sender = new("testtype", "testkey");

        // Act
        MessageEnvelope result = envelope.WithSender(sender);

        // Assert
        Assert.Same(envelope, result);
        Assert.Equal(sender, envelope.Sender);
    }

    [Fact]
    public async Task ForSendTestAsync()
    {
        // Arrange
        MessageEnvelope envelope = new("test");
        ActorId receiver = new("receivertype", "receiverkey");
        object expectedResult = new { Response = "Success" };

        ValueTask<object?> servicer(MessageEnvelope env, CancellationToken ct) => new(expectedResult);

        // Act
        MessageDelivery delivery = envelope.ForSend(receiver, servicer);

        // Assert
        Assert.NotNull(delivery);
        Assert.Same(envelope, delivery.Message);
        Assert.Equal(receiver, envelope.Receiver);

        // Invoke the servicer to verify result sink works
        await delivery.InvokeAsync(CancellationToken.None);
        Assert.True(delivery.ResultTask.IsCompleted);
        object? result = await delivery.ResultTask;
        Assert.Same(expectedResult, result);
    }

    [Fact]
    public void ForPublishTest()
    {
        // Arrange
        MessageEnvelope envelope = new("test");
        TopicId topic = new("testtopic");

        static ValueTask servicer(MessageEnvelope env, CancellationToken ct) => default;

        // Act
        MessageDelivery delivery = envelope.ForPublish(topic, servicer);

        // Assert
        Assert.NotNull(delivery);
        Assert.Same(envelope, delivery.Message);
        Assert.Equal(topic, envelope.Topic);
    }
}
