// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Skills.Mcp.UnitTests;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

[Collection(nameof(McpFeatureUsageActivationTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests()
    {
        ResetFeatureUsage();
    }

    [Fact]
    public async Task ListAgentToolsWithTasksAsync_ActivatesCoreMcpAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools =
        [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        ResetFeatureUsage();

        // Act
        _ = await fixture.Client.ListAgentToolsWithTasksAsync();

        // Assert
        Assert.Equal("v1.4000", GetFeatureToken());
    }

    [Fact]
    public async Task McpSkillsSource_ActivatesOnlyWhenLoadedAsync()
    {
        // Arrange
        await using var server = new InMemoryMcpServer(_ => { });
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);
        ResetFeatureUsage();
        Assert.Null(GetFeatureToken());

        // Act
        _ = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal("v1.80000", GetFeatureToken());
    }

    public void Dispose()
    {
        ResetFeatureUsage();
    }

    private static string? GetFeatureToken()
        => (string?)typeof(FeatureUsage)
            .GetMethod("GetToken", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);

    private static void ResetFeatureUsage()
        => typeof(FeatureUsage)
            .GetMethod("ResetStateForTests", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);
}

[CollectionDefinition(nameof(McpFeatureUsageActivationTestGroup), DisableParallelization = true)]
public sealed class McpFeatureUsageActivationTestGroup;
