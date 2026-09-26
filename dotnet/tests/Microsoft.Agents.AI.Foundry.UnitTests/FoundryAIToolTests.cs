// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

public class FoundryAIToolTests
{
    [Fact]
    public void CreateComputerTool_Parameterless_SerializesAsGaComputerTool()
    {
        // Arrange & Act
        AITool tool = FoundryAITool.CreateComputerTool();

        // Assert
        var responseTool = Assert.IsAssignableFrom<ResponseTool>(tool.GetService(typeof(ResponseTool)));
        string json = ModelReaderWriter.Write(responseTool, ModelReaderWriterOptions.Json).ToString();

        // The GA tool has no environment or display settings; anything besides the type would be a preview field.
        Assert.Equal("{\"type\":\"computer\"}", json);
    }

    [Fact]
    public async Task CreateComputerTool_Parameterless_IsSentAsGaComputerToolOnTheWireAsync()
    {
        // Arrange
        string? requestBody = null;
        using var handler = new HttpHandlerAssert(async request =>
        {
            requestBody = await request.Content!.ReadAsStringAsync();
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    File.ReadAllText(Path.Combine("TestData", "OpenAIDefaultResponse.json")),
                    Encoding.UTF8,
                    "application/json"),
            };
        });
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        IChatClient chatClient = new OpenAIClient(
                new ApiKeyCredential("test-key"),
                new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(httpClient) })
            .GetResponsesClient()
            .AsIChatClient("test-model");

        // Act
        await chatClient.GetResponseAsync("Take a screenshot.", new ChatOptions { Tools = [FoundryAITool.CreateComputerTool()] });

        // Assert
        Assert.NotNull(requestBody);
        using JsonDocument body = JsonDocument.Parse(requestBody!);
        JsonElement tool = Assert.Single(body.RootElement.GetProperty("tools").EnumerateArray());
        Assert.Equal("{\"type\":\"computer\"}", tool.GetRawText());
    }

    [Fact]
    public void CreateComputerTool_WithEnvironmentAndDisplay_SerializesAsPreviewTool()
    {
        // Arrange & Act
        AITool tool = FoundryAITool.CreateComputerTool(ComputerToolEnvironment.Browser, 1024, 768);

        // Assert
        var responseTool = Assert.IsAssignableFrom<ResponseTool>(tool.GetService(typeof(ResponseTool)));
        string json = ModelReaderWriter.Write(responseTool, ModelReaderWriterOptions.Json).ToString();
        Assert.Contains("\"type\":\"computer_use_preview\"", json);
        Assert.Contains("\"environment\":\"browser\"", json);
        Assert.Contains("\"display_width\":1024", json);
        Assert.Contains("\"display_height\":768", json);
    }

    [Fact]
    public void CreateMcpTool_WithProjectConnectionId_SetsProjectConnectionId()
    {
        // Arrange
        const string ConnectionId = "my-foundry-connection";

        // Act
        AITool tool = FoundryAITool.CreateMcpTool(
            serverLabel: "github",
            serverUri: new Uri("https://api.githubcopilot.com/mcp"),
            projectConnectionId: ConnectionId,
            toolCallApprovalPolicy: new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.AlwaysRequireApproval));

        // Assert
        var mcpTool = Assert.IsType<McpTool>(tool.GetService(typeof(McpTool)));
        Assert.Equal(ConnectionId, mcpTool.ProjectConnectionId);
    }

    [Fact]
    public void CreateMcpTool_WithProjectConnectionId_SerializesProjectConnectionId()
    {
        // Arrange
        const string ConnectionId = "my-foundry-connection";

        // Act
        AITool tool = FoundryAITool.CreateMcpTool(
            serverLabel: "github",
            serverUri: new Uri("https://api.githubcopilot.com/mcp"),
            projectConnectionId: ConnectionId);

        // Assert
        var mcpTool = Assert.IsType<McpTool>(tool.GetService(typeof(McpTool)));
        string json = ModelReaderWriter.Write(mcpTool, ModelReaderWriterOptions.Json).ToString();
        Assert.Contains("\"project_connection_id\":\"my-foundry-connection\"", json);
        Assert.Contains("\"server_url\":\"https://api.githubcopilot.com/mcp\"", json);
    }

    [Fact]
    public void CreateMcpTool_WithoutProjectConnectionId_DoesNotEmitProjectConnectionId()
    {
        // Arrange & Act
        AITool tool = FoundryAITool.CreateMcpTool(
            serverLabel: "github",
            serverUri: new Uri("https://api.githubcopilot.com/mcp"));

        // Assert
        var mcpTool = Assert.IsType<McpTool>(tool.GetService(typeof(McpTool)));
        Assert.Null(mcpTool.ProjectConnectionId);
        string json = ModelReaderWriter.Write(mcpTool, ModelReaderWriterOptions.Json).ToString();
        Assert.DoesNotContain("project_connection_id", json);
    }

    [Fact]
    public void CreateMcpTool_WithProjectConnectionIdAndOtherSettings_PreservesAllSettings()
    {
        // Arrange
        const string ConnectionId = "my-foundry-connection";
        const string Token = "my-token";

        // Act
        AITool tool = FoundryAITool.CreateMcpTool(
            serverLabel: "github",
            serverUri: new Uri("https://api.githubcopilot.com/mcp"),
            authorizationToken: Token,
            serverDescription: "GitHub MCP",
            headers: new Dictionary<string, string> { ["X-Custom"] = "value" },
            allowedTools: new McpToolFilter { ToolNames = { "search_issues" } },
            projectConnectionId: ConnectionId);

        // Assert
        var mcpTool = Assert.IsType<McpTool>(tool.GetService(typeof(McpTool)));
        Assert.Equal(ConnectionId, mcpTool.ProjectConnectionId);
        Assert.Equal(Token, mcpTool.AuthorizationToken);
        Assert.Equal("GitHub MCP", mcpTool.ServerDescription);
        Assert.Contains("X-Custom", mcpTool.Headers);
        Assert.Contains("search_issues", mcpTool.AllowedTools.ToolNames);
    }
}
