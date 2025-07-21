// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

public class AgentThreadTests
{
    [Fact]
    public void ConstructorSetsDefaults()
    {
        // Arrange & Act
        var thread = new AgentThread();

        // Assert
        Assert.Null(thread.Id);
    }

    [Fact]
    public void ConstructorFromJsonSetsValues()
    {
        // Arrange
        var json = JsonSerializer.Deserialize<JsonElement>("\"thread-123\"");

        // Act
        var thread = new AgentThread(json, null);

        // Assert
        Assert.Equal("thread-123", thread.Id);
    }

    [Fact]
    public void ConstructorWithInvalidJsonThrows()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize<JsonElement>("{\"notAString\":42}");

        // Act & Assert
        Assert.Throws<JsonException>(() => new AgentThread(invalidJson, null));
    }

    [Fact]
    public void SerializeReturnsJsonStringOfId()
    {
        // Arrange
        var thread = new AgentThread();
        thread.Id = "abc";

        // Act
        var json = thread.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.String, json.ValueKind);
        Assert.Equal("abc", json.ToString());
    }

    [Fact]
    public async Task OnNewMessagesAsyncSucceedsAsync()
    {
        // Arrange
        var thread = new AgentThread();
        var messages = new List<ChatMessage>();

        // Act
        await thread.OnNewMessagesAsync(messages, CancellationToken.None);
    }
}
