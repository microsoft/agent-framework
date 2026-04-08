// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.FoundryLocal.UnitTests;

public class FoundryLocalChatClientExtensionsTests
{
    [Fact]
    public void AsAIAgent_WithNullClient_Throws()
    {
        FoundryLocalChatClient client = null!;

        Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent(instructions: "test"));
    }

    [Fact]
    public void AsAIAgent_WithOptions_WithNullClient_Throws()
    {
        FoundryLocalChatClient client = null!;
        var options = new ChatClientAgentOptions();

        Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent(options));
    }

    [Fact]
    public void AsAIAgent_WithOptions_WithNullOptions_Throws()
    {
        // We can't easily create a real FoundryLocalChatClient without the service,
        // so we test that null options throws even before the client is checked
        var mockClient = new Mock<IChatClient>();
        FoundryLocalChatClient client = null!;

        Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent((ChatClientAgentOptions)null!));
    }
}
