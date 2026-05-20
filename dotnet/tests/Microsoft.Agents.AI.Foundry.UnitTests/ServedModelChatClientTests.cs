// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for <see cref="ServedModelChatClient"/>: the <see cref="DelegatingChatClient"/>
/// that pushes a fresh box onto <see cref="ServedModelScope"/> before each inner call and
/// overwrites <see cref="ChatResponse.ModelId"/> / <see cref="ChatResponseUpdate.ModelId"/>
/// with the value captured by <see cref="ServedModelPolicy"/>.
/// </summary>
public sealed class ServedModelChatClientTests
{
    #region Non-streaming

    [Fact]
    public async Task GetResponseAsync_PolicySetsBox_OverwritesModelIdAsync()
    {
        // Arrange: fake inner client that simulates the policy writing into the box during the call.
        var inner = new ServedModelTestHelpers.FakeChatClientWithPolicySimulation("deployment-alias", "gpt-5-nano-2025-08-07");
        var client = new ServedModelChatClient(inner);

        // Act
        var response = await client.GetResponseAsync([]);

        // Assert
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    [Fact]
    public async Task GetResponseAsync_PolicyDoesNotSetBox_PreservesOriginalModelIdAsync()
    {
        // Arrange: fake inner client that does NOT write to the box (simulates absent header).
        var inner = new ServedModelTestHelpers.FakeChatClient("deployment-alias");
        var client = new ServedModelChatClient(inner);

        // Act
        var response = await client.GetResponseAsync([]);

        // Assert
        Assert.Equal("deployment-alias", response.ModelId);
    }

    #endregion

    #region Streaming

    [Fact]
    public async Task GetStreamingResponseAsync_PolicySetsBox_OverwritesModelIdOnAllUpdatesAsync()
    {
        // Arrange: fake inner client that simulates the policy writing into the box.
        var inner = new ServedModelTestHelpers.FakeStreamingChatClientWithPolicySimulation("deployment-alias", "gpt-5-nano-2025-08-07", updateCount: 3);
        var client = new ServedModelChatClient(inner);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in client.GetStreamingResponseAsync([]))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, updates.Count);
        Assert.All(updates, u => Assert.Equal("gpt-5-nano-2025-08-07", u.ModelId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_PolicyDoesNotSetBox_PreservesOriginalModelIdAsync()
    {
        // Arrange: fake inner client that does NOT write to the box.
        var inner = new ServedModelTestHelpers.FakeStreamingChatClient("deployment-alias", updateCount: 2);
        var client = new ServedModelChatClient(inner);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in client.GetStreamingResponseAsync([]))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.All(updates, u => Assert.Equal("deployment-alias", u.ModelId));
    }

    #endregion

    #region End-to-end (policy + client together via real OpenAI SCM pipeline)

    [Fact]
    public async Task EndToEnd_PolicyAndClient_ModelIdReflectsServedModelAsync()
    {
        // Arrange
        using var handler = new ServedModelTestHelpers.ServedModelHandler(ServedModelTestHelpers.MinimalResponseJson(), servedModel: "gpt-5-nano-2025-08-07");
        IChatClient chatClient = ServedModelTestHelpers.CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }

    [Fact]
    public async Task EndToEnd_PolicyAndClient_NoHeader_ModelIdUnchangedAsync()
    {
        // Arrange
        using var handler = new ServedModelTestHelpers.ServedModelHandler(ServedModelTestHelpers.MinimalResponseJson(), servedModel: null);
        IChatClient chatClient = ServedModelTestHelpers.CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert
        Assert.Equal("fake", response.ModelId);
    }

    #endregion
}
