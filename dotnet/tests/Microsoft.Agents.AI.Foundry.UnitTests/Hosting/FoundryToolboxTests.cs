// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

#pragma warning disable OPENAI001
#pragma warning disable AAIP001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for the <see cref="FoundryToolbox"/> class.
/// </summary>
public class FoundryToolboxTests
{
    private static readonly Uri s_testEndpoint = new("https://test.services.ai.azure.com/api/projects/test-project");

    #region Parameter validation tests

    [Fact]
    public async Task GetToolboxVersionAsync_NullEndpoint_ThrowsAsync()
    {
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryToolbox.GetToolboxVersionAsync(
                projectEndpoint: null!,
                credential: new FakeAuthenticationTokenProvider(),
                name: "test-toolbox"));
    }

    [Fact]
    public async Task GetToolboxVersionAsync_NullCredential_ThrowsAsync()
    {
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryToolbox.GetToolboxVersionAsync(
                projectEndpoint: s_testEndpoint,
                credential: null!,
                name: "test-toolbox"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public async Task GetToolboxVersionAsync_InvalidName_ThrowsAsync(string? name)
    {
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            FoundryToolbox.GetToolboxVersionAsync(
                projectEndpoint: s_testEndpoint,
                credential: new FakeAuthenticationTokenProvider(),
                name: name!));
    }

    [Fact]
    public async Task GetToolsAsync_NullEndpoint_ThrowsAsync()
    {
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            FoundryToolbox.GetToolsAsync(
                projectEndpoint: null!,
                credential: new FakeAuthenticationTokenProvider(),
                name: "test-toolbox"));
    }

    [Fact]
    public void ToAITools_NullToolboxVersion_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            FoundryToolbox.ToAITools(null!));
    }

    #endregion

    #region ToAITools conversion tests

    [Fact]
    public void ToAITools_EmptyTools_ReturnsEmptyList()
    {
        var version = ProjectsAgentsModelFactory.ToolboxVersion(
            metadata: null,
            id: "ver-1",
            name: "empty-toolbox",
            version: "v1",
            description: "Empty",
            createdAt: DateTimeOffset.UtcNow,
            tools: Array.Empty<ProjectsAgentTool>(),
            policies: null);

        var tools = version.ToAITools();

        Assert.Empty(tools);
    }

    [Fact]
    public void ToAITools_NullTools_ReturnsEmptyList()
    {
        var version = ProjectsAgentsModelFactory.ToolboxVersion(
            metadata: null,
            id: "ver-1",
            name: "null-tools-toolbox",
            version: "v1",
            description: "Null tools",
            createdAt: DateTimeOffset.UtcNow,
            tools: null,
            policies: null);

        var tools = version.ToAITools();

        Assert.Empty(tools);
    }

    [Fact]
    public void ToAITools_WithCodeInterpreterTool_ReturnsAITool()
    {
        var json = TestDataUtil.GetToolboxVersionResponseJson();
        var version = ModelReaderWriter.Read<ToolboxVersion>(BinaryData.FromString(json))!;

        var tools = version.ToAITools();

        Assert.Single(tools);
        Assert.IsAssignableFrom<AITool>(tools[0]);
    }

    [Fact]
    public void ToAITools_SanitizesDecorationFieldsOnNonFunctionTools()
    {
        var json = TestDataUtil.GetToolboxVersionWithDecorationFieldsJson();
        var version = ModelReaderWriter.Read<ToolboxVersion>(BinaryData.FromString(json))!;

        var tools = version.ToAITools();

        Assert.Single(tools);
        Assert.IsAssignableFrom<AITool>(tools[0]);
    }

    [Fact]
    public void SanitizeAndConvert_FunctionTool_PreservesNameAndDescription()
    {
        const string ToolJson = @"{""type"":""function"",""name"":""get_weather"",""description"":""Get weather"",""parameters"":{""type"":""object"",""properties"":{}}}";
        var tool = ModelReaderWriter.Read<ProjectsAgentTool>(BinaryData.FromString(ToolJson))!;

        var aiTool = FoundryToolbox.SanitizeAndConvert(tool);

        Assert.NotNull(aiTool);
        Assert.IsAssignableFrom<AITool>(aiTool);
    }

    [Fact]
    public void SanitizeAndConvert_CodeInterpreterWithExtraFields_StripsDecorationFields()
    {
        const string ToolJson = @"{""type"":""code_interpreter"",""name"":""code_interpreter"",""description"":""Execute code""}";
        var tool = ModelReaderWriter.Read<ProjectsAgentTool>(BinaryData.FromString(ToolJson))!;

        var aiTool = FoundryToolbox.SanitizeAndConvert(tool);

        Assert.NotNull(aiTool);
    }

    #endregion

    #region Integration tests with mock HTTP

    [Fact]
    public async Task GetToolboxVersionAsync_WithExplicitVersion_FetchesVersionDirectlyAsync()
    {
        var versionJson = TestDataUtil.GetToolboxVersionResponseJson();
        using var httpHandler = new HttpHandlerAssert((request) =>
        {
            Assert.Contains("/toolboxes/research_tools/versions/v5", request.RequestUri!.PathAndQuery);

            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(versionJson, Encoding.UTF8, "application/json")
            };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399
        var clientOptions = new AgentAdministrationClientOptions { Transport = new HttpClientPipelineTransport(httpClient) };

        var result = await FoundryToolbox.GetToolboxVersionAsync(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            "research_tools",
            version: "v5",
            clientOptions: clientOptions,
            cancellationToken: default);

        Assert.Equal("research_tools", result.Name);
        Assert.Equal("v5", result.Version);
        Assert.Single(result.Tools);
    }

    [Fact]
    public async Task GetToolboxVersionAsync_WithoutVersion_ResolvesDefaultThenFetchesAsync()
    {
        var recordJson = TestDataUtil.GetToolboxRecordResponseJson();
        var versionJson = TestDataUtil.GetToolboxVersionResponseJson();
        var callCount = 0;

        using var httpHandler = new HttpHandlerAssert((request) =>
        {
            callCount++;
            var path = request.RequestUri!.PathAndQuery;

            if (!path.Contains("/versions/"))
            {
                Assert.Contains("/toolboxes/research_tools", path);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(recordJson, Encoding.UTF8, "application/json")
                };
            }

            Assert.Contains("/toolboxes/research_tools/versions/v5", path);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(versionJson, Encoding.UTF8, "application/json")
            };
        });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399
        var clientOptions = new AgentAdministrationClientOptions { Transport = new HttpClientPipelineTransport(httpClient) };

        var result = await FoundryToolbox.GetToolboxVersionAsync(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            "research_tools",
            version: null,
            clientOptions: clientOptions,
            cancellationToken: default);

        Assert.Equal(2, callCount);
        Assert.Equal("research_tools", result.Name);
        Assert.Equal("v5", result.Version);
    }

    [Fact]
    public async Task GetToolboxVersionAsync_ApiError_ThrowsClientResultExceptionAsync()
    {
        using var httpHandler = new HttpHandlerAssert((_) =>
            new HttpResponseMessage(HttpStatusCode.NotFound)
            {
                Content = new StringContent("{\"error\":\"not found\"}", Encoding.UTF8, "application/json")
            });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399
        var clientOptions = new AgentAdministrationClientOptions { Transport = new HttpClientPipelineTransport(httpClient) };

        await Assert.ThrowsAsync<ClientResultException>(() =>
            FoundryToolbox.GetToolboxVersionAsync(
                s_testEndpoint,
                new FakeAuthenticationTokenProvider(),
                "nonexistent-toolbox",
                version: "v1",
                clientOptions: clientOptions,
                cancellationToken: default));
    }

    [Fact]
    public async Task GetToolsAsync_ReturnsConvertedAIToolsAsync()
    {
        var versionJson = TestDataUtil.GetToolboxVersionResponseJson();
        using var httpHandler = new HttpHandlerAssert((_) =>
            new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(versionJson, Encoding.UTF8, "application/json")
            });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399
        var clientOptions = new AgentAdministrationClientOptions { Transport = new HttpClientPipelineTransport(httpClient) };

        var result = await FoundryToolbox.GetToolboxVersionAsync(
            s_testEndpoint,
            new FakeAuthenticationTokenProvider(),
            "research_tools",
            version: "v5",
            clientOptions: clientOptions,
            cancellationToken: default);

        var tools = result.ToAITools();

        Assert.Single(tools);
        Assert.IsAssignableFrom<AITool>(tools[0]);
    }

    #endregion

    #region AIProjectClient extension tests

    [Fact]
    public async Task AIProjectClientExtension_GetToolboxToolsAsync_ReturnsAIToolsAsync()
    {
        var versionJson = TestDataUtil.GetToolboxVersionResponseJson();
        using var httpHandler = new HttpHandlerAssert((_) =>
            new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(versionJson, Encoding.UTF8, "application/json")
            });

#pragma warning disable CA5399
        using var httpClient = new HttpClient(httpHandler);
#pragma warning restore CA5399
        var clientOptions = new AIProjectClientOptions();
        clientOptions.Transport = new HttpClientPipelineTransport(httpClient);
        var client = new AIProjectClient(s_testEndpoint, new FakeAuthenticationTokenProvider(), clientOptions);

        var tools = await client.GetToolboxToolsAsync("research_tools", version: "v5");

        Assert.Single(tools);
        Assert.IsAssignableFrom<AITool>(tools[0]);
    }

    #endregion
}
