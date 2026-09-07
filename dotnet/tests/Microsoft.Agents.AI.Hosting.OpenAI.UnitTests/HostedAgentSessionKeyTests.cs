// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for choosing an agent session key from Responses continuation identifiers.
/// </summary>
public sealed class HostedAgentSessionKeyTests
{
    [Theory]
    [InlineData("conv_1", null, "resp_new", "conv_1")]
    [InlineData(null, "resp_previous", "resp_new", "resp_previous")]
    [InlineData(null, null, "resp_new", "resp_new")]
    [InlineData("", "resp_previous", "resp_new", "resp_previous")]
    [InlineData(" ", "\t", "resp_new", "resp_new")]
    [InlineData("opaque:conversation/key", null, "resp_new", "opaque:conversation/key")]
    public void Resolve_UsesAvailableContinuationKey(string? conversationId, string? previousResponseId, string responseId, string expected)
    {
        // Arrange & Act
        string result = HostedAgentSessionKey.Resolve(conversationId, previousResponseId, responseId);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void Resolve_PreviousResponsesWithCommonPrefix_RemainDistinct()
    {
        // Arrange - Even IDs shaped like Foundry IDs must not be reduced to their shared partition.
        string firstId = "resp_" + new string('a', 18) + new string('b', 32);
        string secondId = "resp_" + new string('a', 18) + new string('c', 32);

        // Act
        string firstKey = HostedAgentSessionKey.Resolve(null, firstId, "resp_new");
        string secondKey = HostedAgentSessionKey.Resolve(null, secondId, "resp_new");

        // Assert
        Assert.Equal(firstId, firstKey);
        Assert.Equal(secondId, secondKey);
        Assert.NotEqual(firstKey, secondKey);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public void Resolve_NoUsableKey_Throws(string? responseId)
    {
        // Arrange & Act & Assert
        Assert.ThrowsAny<ArgumentException>(() => HostedAgentSessionKey.Resolve(null, null, responseId!));
    }
}
