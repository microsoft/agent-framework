// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests selection between <c>skills/list</c> and <c>skill://index.json</c> based on the server's Skills extension.
/// </summary>
public sealed class AgentMcpSkillsDiscoverySelectionTests
{
    [Theory]
    [InlineData("{}")]
    [InlineData("""{"extensions":null}""")]
    [InlineData("""{"extensions":{}}""")]
    [InlineData("""{"extensions":{"example.test/other":{}}}""")]
    [InlineData("""{"extensions":{"IO.MODELCONTEXTPROTOCOL/SKILLS":{}}}""")]
    public async Task GetSkillsAsync_AbsentSkillsKey_ReadsIndexAsync(string capabilitiesJson)
    {
        // Arrange
        List<string> requests = [];
        await using var server = CreateServer(requests);
        await using var client = await server.CreateClientAsync();
        client.ServerCapabilities.Extensions = JsonSerializer.Deserialize<ServerCapabilities>(capabilitiesJson)!.Extensions;
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
        Assert.Equal("skill://index.json", Assert.Single(requests));
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("""{"directoryRead":true}""")]
    [InlineData("""{"directoryRead":false}""")]
    [InlineData("""{"futureSetting":{"nested":42}}""")]
    [InlineData("null")]
    [InlineData("true")]
    [InlineData("false")]
    [InlineData("42")]
    [InlineData("[]")]
    [InlineData("\"supported\"")]
    [InlineData("""{"directoryRead":null}""")]
    [InlineData("""{"directoryRead":"true"}""")]
    [InlineData("""{"directoryRead":1}""")]
    [InlineData("""{"directoryRead":[]}""")]
    [InlineData("""{"directoryRead":{}}""")]
    public async Task GetSkillsAsync_PresentSkillsKey_ListsSkillsAsync(string declaration)
    {
        // Arrange
        List<string> requests = [];
        await using var server = CreateServer(requests);
        await using var client = await server.CreateClientAsync();
        client.ServerCapabilities.Extensions = CreateCapabilities(declaration).Extensions;
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
        Assert.Equal("skills/list", Assert.Single(requests));
    }

    [Fact]
    public async Task GetSkillsAsync_MissingResourcesCapability_ListsSkillsAsync()
    {
        // Arrange
        List<string> requests = [];
        await using var server = CreateServer(requests);
        await using var client = await server.CreateClientAsync();
        client.ServerCapabilities.Extensions = CreateCapabilities("{}").Extensions;
        client.ServerCapabilities.Resources = null;
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
        Assert.Equal("skills/list", Assert.Single(requests));
    }

    private static ServerCapabilities CreateCapabilities(string declaration) =>
        JsonSerializer.Deserialize<ServerCapabilities>(
            """{"resources":{},"extensions":{"io.modelcontextprotocol/skills":""" + declaration + "}}")!;

#pragma warning disable MCPEXP002 // Custom extension methods require raw server request handlers.
    private static InMemoryMcpServer CreateServer(List<string> requests) =>
        new(builder => builder.WithReadResourceHandler((request, _) =>
        {
            string uri = request.Params!.Uri;
            requests.Add(uri);
            return ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents { Uri = uri, Text = """{"skills":[]}""" }],
            });
        }), options =>
        {
            options.RequestHandlers =
            [
                new()
                {
                    Method = "skills/list",
                    Handler = (_, _) =>
                    {
                        requests.Add("skills/list");
                        return ValueTask.FromResult(JsonNode.Parse("""{"resultType":"complete","skills":[]}"""));
                    },
                },
            ];
        });
#pragma warning restore MCPEXP002
}
