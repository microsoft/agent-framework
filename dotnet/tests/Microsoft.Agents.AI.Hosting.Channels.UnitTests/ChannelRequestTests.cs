// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

public class ChannelRequestTests
{
    [Fact]
    public void ChannelRequest_DefaultsAreMinimal()
    {
        // Arrange / Act
        var request = new ChannelRequest("responses", "message.create", "hello");

        // Assert
        Assert.Equal(SessionMode.Auto, request.SessionMode);
        Assert.False(request.Stream);
        Assert.Null(request.Session);
        Assert.Null(request.Identity);
        Assert.Empty(request.Attributes);
        Assert.Empty(request.Metadata);
    }

    [Fact]
    public void ChannelSession_AllFieldsNullable()
    {
        // Arrange / Act
        var session = new ChannelSession();

        // Assert
        Assert.Null(session.Key);
        Assert.Null(session.ConversationId);
        Assert.Null(session.IsolationKey);
    }
}
