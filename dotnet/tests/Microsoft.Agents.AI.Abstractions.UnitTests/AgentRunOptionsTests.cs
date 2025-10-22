// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunOptions"/> class.
/// </summary>
public class AgentRunOptionsTests
{
    [Fact]
    public void CloningConstructorCopiesProperties()
    {
        // Arrange
        var options = new AgentRunOptions
        {
            ContinuationToken = new object(),
            AllowBackgroundResponses = true
        };

        // Act
        var clone = new AgentRunOptions(options);

        // Assert
        Assert.NotNull(clone);
        Assert.Same(options.ContinuationToken, clone.ContinuationToken);
        Assert.Equal(options.AllowBackgroundResponses, clone.AllowBackgroundResponses);
    }

    [Fact]
    public void CloningConstructorThrowsIfNull() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunOptions(null!));

    [Fact]
    public void JsonSerializationRoundtrips()
    {
        // Arrange
        var options = new AgentRunOptions
        {
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
            AllowBackgroundResponses = true
        };

        // Act
        string json = JsonSerializer.Serialize(options, AgentAbstractionsJsonUtilities.DefaultOptions);

        var deserialized = JsonSerializer.Deserialize<AgentRunOptions>(json, AgentAbstractionsJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equivalent(ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }), deserialized!.ContinuationToken);
        Assert.Equal(options.AllowBackgroundResponses, deserialized.AllowBackgroundResponses);
    }
}
