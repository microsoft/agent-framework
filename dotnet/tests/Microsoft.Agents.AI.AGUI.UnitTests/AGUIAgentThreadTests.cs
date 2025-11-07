// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

public sealed class AGUIAgentThreadTests
{
    [Fact]
    public void Constructor_WithValidThreadId_DeserializesSuccessfully()
    {
        // Arrange
        const string ThreadId = "thread123";
        AGUIAgentThread originalThread = new() { ThreadId = ThreadId };
        JsonElement serialized = originalThread.Serialize();

        // Act
        AGUIAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Equal(ThreadId, deserializedThread.ThreadId);
    }

    [Fact]
    public void Constructor_WithMissingThreadId_ThrowsInvalidOperationException()
    {
        // Arrange
        const string Json = """
            {"WrappedState":{}}
            """;
        JsonElement serialized = JsonSerializer.Deserialize<JsonElement>(Json);

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => new AGUIAgentThread(serialized));
    }

    [Fact]
    public void Constructor_WithMissingWrappedState_ThrowsArgumentException()
    {
        // Arrange
        const string Json = """
            {}
            """;
        JsonElement serialized = JsonSerializer.Deserialize<JsonElement>(Json);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AGUIAgentThread(serialized));
    }

    [Fact]
    public async Task Constructor_UnwrapsAndRestores_BaseStateAsync()
    {
        // Arrange
        AGUIAgentThread originalThread = new() { ThreadId = "thread1" };
        ChatMessage message = new(ChatRole.User, "Test message");
        await TestAgent.AddMessageToThreadAsync(originalThread, message);
        JsonElement serialized = originalThread.Serialize();

        // Act
        AGUIAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Single(deserializedThread.MessageStore);
        Assert.Equal("Test message", deserializedThread.MessageStore.First().Text);
    }

    [Fact]
    public void Serialize_IncludesThreadId_InSerializedState()
    {
        // Arrange
        const string ThreadId = "thread456";
        AGUIAgentThread thread = new() { ThreadId = ThreadId };

        // Act
        JsonElement serialized = thread.Serialize();

        // Assert
        Assert.True(serialized.TryGetProperty("ThreadId", out JsonElement threadIdElement));
        Assert.Equal(ThreadId, threadIdElement.GetString());
    }

    [Fact]
    public async Task Serialize_WrapsBaseState_CorrectlyAsync()
    {
        // Arrange
        AGUIAgentThread thread = new() { ThreadId = "thread1" };
        ChatMessage message = new(ChatRole.User, "Test message");
        await TestAgent.AddMessageToThreadAsync(thread, message);

        // Act
        JsonElement serialized = thread.Serialize();

        // Assert
        Assert.True(serialized.TryGetProperty("WrappedState", out JsonElement wrappedState));
        Assert.NotEqual(JsonValueKind.Null, wrappedState.ValueKind);
    }

    [Fact]
    public async Task Serialize_RoundTrip_PreservesThreadIdAndMessagesAsync()
    {
        // Arrange
        const string ThreadId = "thread789";
        AGUIAgentThread originalThread = new() { ThreadId = ThreadId };
        ChatMessage message1 = new(ChatRole.User, "First message");
        ChatMessage message2 = new(ChatRole.Assistant, "Second message");
        await TestAgent.AddMessageToThreadAsync(originalThread, message1);
        await TestAgent.AddMessageToThreadAsync(originalThread, message2);

        // Act
        JsonElement serialized = originalThread.Serialize();
        AGUIAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Equal(ThreadId, deserializedThread.ThreadId);
        Assert.Equal(2, deserializedThread.MessageStore.Count);
        Assert.Equal("First message", deserializedThread.MessageStore.ElementAt(0).Text);
        Assert.Equal("Second message", deserializedThread.MessageStore.ElementAt(1).Text);
    }

    private abstract class TestAgent : AIAgent
    {
        public static async Task AddMessageToThreadAsync(AgentThread thread, ChatMessage message)
        {
            await NotifyThreadOfNewMessagesAsync(thread, [message], CancellationToken.None);
        }
    }
}
