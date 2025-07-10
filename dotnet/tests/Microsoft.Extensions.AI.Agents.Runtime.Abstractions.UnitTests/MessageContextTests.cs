// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class MessageContextTests
{
    [Fact]
    public void Properties_Roundtrip()
    {
        MessageContext ctx = new();

        string id = ctx.MessageId;
        Assert.NotNull(id);
        Assert.True(Guid.TryParse(id, out _));
        ctx.MessageId = "newid";
        Assert.Equal("newid", ctx.MessageId);

        Assert.False(ctx.IsRpc);
        ctx.IsRpc = true;
        Assert.True(ctx.IsRpc);

        Assert.Null(ctx.Sender);
        ActorId sender = new("type", "key");
        ctx.Sender = sender;
        Assert.Equal(sender, ctx.Sender);

        Assert.Null(ctx.Topic);
        TopicId topic = new("type", "source");
        ctx.Topic = topic;
        Assert.Equal(topic, ctx.Topic);
    }
}
