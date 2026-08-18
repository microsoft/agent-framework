// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AIAgentsAbstractionsExtensionsTests
{
    [Fact]
    public void CopyWithAssistantToUserForOtherParticipants_DoesNotMutateOriginalMessages()
    {
        ChatMessage original = new(ChatRole.Assistant, "from first agent")
        {
            AuthorName = "firstAgent"
        };

        List<ChatMessage> copied = new[] { original }
            .CopyWithAssistantToUserForOtherParticipants("secondAgent");

        Assert.Single(copied);
        Assert.Equal(ChatRole.Assistant, original.Role);
        Assert.Equal(ChatRole.User, copied[0].Role);
        Assert.NotSame(original, copied[0]);
    }
}
