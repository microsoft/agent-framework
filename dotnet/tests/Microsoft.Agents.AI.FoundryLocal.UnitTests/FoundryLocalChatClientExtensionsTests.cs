// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

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
        // When both arguments are null, AsAIAgent validates client first.
        // This test therefore verifies the null-client guard, not the null-options path.
        FoundryLocalChatClient client = null!;

        var exception = Assert.Throws<ArgumentNullException>(() =>
            client.AsAIAgent((ChatClientAgentOptions)null!));

        Assert.Equal("client", exception.ParamName);
    }
}
