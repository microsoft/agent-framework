// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ToolApprovalRule"/> class.
/// </summary>
public class ToolApprovalRuleTests
{
    #region Construction and Defaults

    /// <summary>
    /// Verify that a new rule has the expected default values.
    /// </summary>
    [Fact]
    public void NewRule_HasDefaultValues()
    {
        // Act
        var rule = new ToolApprovalRule();

        // Assert
        Assert.Equal(string.Empty, rule.ToolName);
        Assert.Null(rule.Arguments);
    }

    /// <summary>
    /// Verify that ToolName can be set.
    /// </summary>
    [Fact]
    public void ToolName_CanBeSet()
    {
        // Arrange & Act
        var rule = new ToolApprovalRule { ToolName = "ReadFile" };

        // Assert
        Assert.Equal("ReadFile", rule.ToolName);
    }

    /// <summary>
    /// Verify that Arguments can be set.
    /// </summary>
    [Fact]
    public void Arguments_CanBeSet()
    {
        // Arrange & Act
        var args = new Dictionary<string, string> { ["path"] = "test.txt" };
        var rule = new ToolApprovalRule { ToolName = "ReadFile", Arguments = args };

        // Assert
        Assert.NotNull(rule.Arguments);
        Assert.Equal("test.txt", rule.Arguments["path"]);
    }

    #endregion

    #region JSON Serialization

    /// <summary>
    /// Verify that a tool-level rule round-trips through JSON serialization.
    /// </summary>
    [Fact]
    public void Serialize_ToolLevelRule_RoundTrips()
    {
        // Arrange
        var rule = new ToolApprovalRule { ToolName = "MyTool" };

        // Act
        var json = JsonSerializer.Serialize(rule, AgentJsonUtilities.DefaultOptions);
        var deserialized = JsonSerializer.Deserialize<ToolApprovalRule>(json, AgentJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("MyTool", deserialized!.ToolName);
        Assert.Null(deserialized.Arguments);
    }

    /// <summary>
    /// Verify that a tool+arguments rule round-trips through JSON serialization.
    /// </summary>
    [Fact]
    public void Serialize_ToolWithArgsRule_RoundTrips()
    {
        // Arrange
        var rule = new ToolApprovalRule
        {
            ToolName = "ReadFile",
            Arguments = new Dictionary<string, string> { ["path"] = "test.txt", ["encoding"] = "utf-8" },
        };

        // Act
        var json = JsonSerializer.Serialize(rule, AgentJsonUtilities.DefaultOptions);
        var deserialized = JsonSerializer.Deserialize<ToolApprovalRule>(json, AgentJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("ReadFile", deserialized!.ToolName);
        Assert.NotNull(deserialized.Arguments);
        Assert.Equal(2, deserialized.Arguments!.Count);
        Assert.Equal("test.txt", deserialized.Arguments["path"]);
        Assert.Equal("utf-8", deserialized.Arguments["encoding"]);
    }

    /// <summary>
    /// Verify that JSON property names are correctly applied.
    /// </summary>
    [Fact]
    public void Serialize_UsesJsonPropertyNames()
    {
        // Arrange
        var rule = new ToolApprovalRule
        {
            ToolName = "MyTool",
            Arguments = new Dictionary<string, string> { ["key"] = "value" },
        };

        // Act
        var json = JsonSerializer.Serialize(rule, AgentJsonUtilities.DefaultOptions);

        // Assert
        Assert.Contains("\"toolName\"", json);
        Assert.Contains("\"arguments\"", json);
    }

    /// <summary>
    /// Verify that a list of rules round-trips through JSON serialization.
    /// </summary>
    [Fact]
    public void Serialize_RuleList_RoundTrips()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new() { ToolName = "ToolA" },
            new() { ToolName = "ToolB", Arguments = new Dictionary<string, string> { ["x"] = "1" } },
        };

        // Act
        var json = JsonSerializer.Serialize(rules, AgentJsonUtilities.DefaultOptions);
        var deserialized = JsonSerializer.Deserialize<List<ToolApprovalRule>>(json, AgentJsonUtilities.DefaultOptions);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(2, deserialized!.Count);
        Assert.Equal("ToolA", deserialized[0].ToolName);
        Assert.Null(deserialized[0].Arguments);
        Assert.Equal("ToolB", deserialized[1].ToolName);
        Assert.NotNull(deserialized[1].Arguments);
    }

    #endregion
}
