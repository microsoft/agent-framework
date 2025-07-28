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
    public async Task DeserializeFromJsonSetsValuesAsync()
    {
        // Arrange
        var json = JsonSerializer.Deserialize<JsonElement>("{\"id\":\"thread-123\"}");
        var thread = new AgentThread();

        // Act
        await thread.DeserializeAsync(json);

        // Assert
        Assert.Equal("thread-123", thread.Id);
    }

    [Fact]
    public async Task DeserializeWithInvalidJsonThrowsAsync()
    {
        // Arrange
        var invalidJson = JsonSerializer.Deserialize<JsonElement>("[42]");
        var thread = new AgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => thread.DeserializeAsync(invalidJson));
    }

    [Fact]
    public async Task SerializeReturnsJsonStringOfIdAsync()
    {
        // Arrange
        var thread = new AgentThread();
        thread.Id = "abc";

        // Act
        var json = await thread.SerializeAsync();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.Equal("{\"id\":\"abc\"}", json.ToString());
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
