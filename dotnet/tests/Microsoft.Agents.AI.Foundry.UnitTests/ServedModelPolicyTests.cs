// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#pragma warning disable OPENAI001, MEAI001, MAAI001, SCME0001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for <see cref="ServedModelPolicy"/>: the SCM pipeline policy that reads the
/// <c>x-ms-served-model</c> response header and writes it into the active
/// <see cref="ServedModelScope"/> box.
/// </summary>
/// <remarks>
/// Tests drive the policy through a real OpenAI ResponsesClient SCM pipeline against a mock
/// HTTP handler so the policy executes in its production configuration.
/// </remarks>
public sealed class ServedModelPolicyTests
{
    [Fact]
    public void Instance_IsSingleton()
    {
        Assert.Same(ServedModelPolicy.Instance, ServedModelPolicy.Instance);
    }

    [Fact]
    public async Task ProcessAsync_HeaderPresent_SetsModelIdOnResponseAsync()
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
    public async Task ProcessAsync_HeaderAbsent_PreservesModelIdFromBodyAsync()
    {
        // Arrange
        using var handler = new ServedModelTestHelpers.ServedModelHandler(ServedModelTestHelpers.MinimalResponseJson(), servedModel: null);
        IChatClient chatClient = ServedModelTestHelpers.CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: ModelId is the deployment alias from the JSON body ("fake").
        Assert.Equal("fake", response.ModelId);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task ProcessAsync_EmptyOrWhitespaceHeader_PreservesModelIdFromBodyAsync(string headerValue)
    {
        // Arrange
        using var handler = new ServedModelTestHelpers.ServedModelHandler(ServedModelTestHelpers.MinimalResponseJson(), servedModel: headerValue);
        IChatClient chatClient = ServedModelTestHelpers.CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert: empty/whitespace header is rejected by the policy, ModelId stays as "fake".
        Assert.Equal("fake", response.ModelId);
    }

    [Fact]
    public async Task ProcessAsync_HeaderWithSurroundingWhitespace_TrimsValueAsync()
    {
        // Arrange
        using var handler = new ServedModelTestHelpers.ServedModelHandler(ServedModelTestHelpers.MinimalResponseJson(), servedModel: "  gpt-5-nano-2025-08-07  ");
        IChatClient chatClient = ServedModelTestHelpers.CreateChatClientWithPolicy(handler);

        // Act
        var response = await chatClient.GetResponseAsync("hi");

        // Assert
        Assert.Equal("gpt-5-nano-2025-08-07", response.ModelId);
    }
}
