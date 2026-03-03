// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Compaction;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

public class MessageGroupTests
{
    [Fact]
    public void Equality_Works()
    {
        // Arrange
        ChatMessageGroup a = new(0, 2, ChatMessageGroupKind.AssistantToolGroup);
        ChatMessageGroup b = new(0, 2, ChatMessageGroupKind.AssistantToolGroup);
        ChatMessageGroup c = new(1, 2, ChatMessageGroupKind.AssistantToolGroup);

        // Act & Assert
        Assert.Equal(a, b);
        Assert.True(a == b);
        Assert.NotEqual(a, c);
        Assert.True(a != c);
    }

    [Fact]
    public void Equals_Object_NullReturnsFalse()
    {
        // Arrange
        ChatMessageGroup group = new(0, 1, ChatMessageGroupKind.System);

        // Act & Assert
        Assert.False(group.Equals(null));
    }

    [Fact]
    public void Equals_Object_BoxedMessageGroupReturnsTrue()
    {
        // Arrange
        ChatMessageGroup group = new(0, 2, ChatMessageGroupKind.AssistantToolGroup);
        object boxed = new ChatMessageGroup(0, 2, ChatMessageGroupKind.AssistantToolGroup);

        // Act & Assert
        Assert.True(group.Equals(boxed));
    }

    [Fact]
    public void Equals_Object_WrongTypeReturnsFalse()
    {
        // Arrange
        ChatMessageGroup group = new(0, 1, ChatMessageGroupKind.System);

        // Act & Assert
        Assert.False(group.Equals("not a MessageGroup"));
    }

    [Fact]
    public void GetHashCode_ConsistentForEqualInstances()
    {
        // Arrange
        ChatMessageGroup a = new(0, 2, ChatMessageGroupKind.AssistantToolGroup);
        ChatMessageGroup b = new(0, 2, ChatMessageGroupKind.AssistantToolGroup);

        // Act & Assert
        Assert.Equal(a.GetHashCode(), b.GetHashCode());
    }
}
