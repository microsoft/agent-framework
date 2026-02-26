// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

/// <summary>
/// Unit tests for the <see cref="DurableAgentRunOptions"/> class.
/// </summary>
public sealed class DurableAgentRunOptionsTests
{
    [Fact]
    public void CloneReturnsNewInstanceWithSameValues()
    {
        // Arrange
        DurableAgentRunOptions options = new()
        {
            EnableToolCalls = false,
            EnableToolNames = new List<string> { "tool1", "tool2" },
            IsFireAndForget = true,
            AllowBackgroundResponses = true,
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["key1"] = "value1",
                ["key2"] = 42
            },
            ResponseFormat = ChatResponseFormat.Json
        };

        // Act
        AgentRunOptions cloneAsBase = options.Clone();

        // Assert
        Assert.NotNull(cloneAsBase);
        Assert.IsType<DurableAgentRunOptions>(cloneAsBase);
        DurableAgentRunOptions clone = (DurableAgentRunOptions)cloneAsBase;
        Assert.NotSame(options, clone);
        Assert.Equal(options.EnableToolCalls, clone.EnableToolCalls);
        Assert.NotNull(clone.EnableToolNames);
        Assert.NotSame(options.EnableToolNames, clone.EnableToolNames);
        Assert.Equal(2, clone.EnableToolNames.Count);
        Assert.Contains("tool1", clone.EnableToolNames);
        Assert.Contains("tool2", clone.EnableToolNames);
        Assert.Equal(options.IsFireAndForget, clone.IsFireAndForget);
        Assert.Equal(options.AllowBackgroundResponses, clone.AllowBackgroundResponses);
        Assert.Same(options.ContinuationToken, clone.ContinuationToken);
        Assert.NotNull(clone.AdditionalProperties);
        Assert.NotSame(options.AdditionalProperties, clone.AdditionalProperties);
        Assert.Equal("value1", clone.AdditionalProperties["key1"]);
        Assert.Equal(42, clone.AdditionalProperties["key2"]);
        Assert.Same(options.ResponseFormat, clone.ResponseFormat);
    }

    [Fact]
    public void CloneCreatesIndependentEnableToolNamesList()
    {
        // Arrange
        DurableAgentRunOptions options = new()
        {
            EnableToolNames = new List<string> { "tool1" }
        };

        // Act
        DurableAgentRunOptions clone = (DurableAgentRunOptions)options.Clone();
        clone.EnableToolNames!.Add("tool2");

        // Assert
        Assert.Equal(2, clone.EnableToolNames.Count);
        Assert.Single(options.EnableToolNames);
        Assert.DoesNotContain("tool2", options.EnableToolNames);
    }

    [Fact]
    public void CloneCreatesIndependentAdditionalPropertiesDictionary()
    {
        // Arrange
        DurableAgentRunOptions options = new()
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["key1"] = "value1"
            }
        };

        // Act
        DurableAgentRunOptions clone = (DurableAgentRunOptions)options.Clone();
        clone.AdditionalProperties!["key2"] = "value2";

        // Assert
        Assert.True(clone.AdditionalProperties.ContainsKey("key2"));
        Assert.False(options.AdditionalProperties.ContainsKey("key2"));
    }
}
