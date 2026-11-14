// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
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
    public async Task HostedImageGenerationTool_StreamingWithoutPartialImages_YieldsFinalImageAsync()
    {
        // Arrange
        const string Output = """
            event: response.created
            data: {"type":"response.created","response":{"id":"resp_final","object":"response","created_at":1741892091,"status":"in_progress","model":"gpt-4o-2024-11-20","output":[]}}

            event: response.output_item.added
            data: {"type":"response.output_item.added","output_index":0,"item":{"type":"image_generation_call","id":"img_call_final","status":"in_progress"}}

            event: response.image_generation_call.in_progress
            data: {"type":"response.image_generation_call.in_progress","item_id":"img_call_final","output_index":0}

            event: response.image_generation_call.generating
            data: {"type":"response.image_generation_call.generating","item_id":"img_call_final","output_index":0}

            event: response.output_item.done
            data: {"type":"response.output_item.done","output_index":0,"item":{"type":"image_generation_call","id":"img_call_final","status":"completed","result":"RmluYWw="}}

            event: response.completed
            data: {"type":"response.completed","response":{"id":"resp_final","object":"response","created_at":1741892091,"status":"completed","model":"gpt-4o-2024-11-20","output":[{"type":"image_generation_call","id":"img_call_final","status":"completed","result":"RmluYWw="}],"usage":{"input_tokens":15,"output_tokens":0,"total_tokens":15}}}


            """;

        using var handler = new HttpHandlerAssert(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(Output, Encoding.UTF8, "text/event-stream"),
        }));
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        IChatClient chatClient = new OpenAIClient(
                new ApiKeyCredential("test-key"),
                new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(httpClient) })
            .GetResponsesClient()
            .AsIChatClient("gpt-4o");
        var imageTool = new HostedImageGenerationTool
        {
            Options = new ImageGenerationOptions
            {
                ModelId = "gpt-image-1",
                MediaType = "image/jpeg",
            },
        };
        List<ChatResponseUpdate> updates = [];

        // Act
        await foreach (ChatResponseUpdate update in chatClient.GetStreamingResponseAsync(
            "Generate an image.",
            new ChatOptions { Tools = [imageTool] }))
        {
            updates.Add(update);
        }

        // Assert
        var result = Assert.Single(updates.SelectMany(update => update.Contents).OfType<ImageGenerationToolResultContent>());
        Assert.Equal("img_call_final", result.CallId);
        Assert.IsType<ImageGenerationCallResponseItem>(result.RawRepresentation);
        var image = Assert.IsType<DataContent>(Assert.Single(result.Outputs!));
        Assert.Equal("image/jpeg", image.MediaType);
        Assert.Equal("Final", Encoding.UTF8.GetString(image.Data.ToArray()));
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
    public void CreateBrowserAutomationTool_ReturnsGaBrowserAutomationTool()
    {
        // Arrange
        var options = new BrowserAutomationToolOptions(new BrowserAutomationToolConnectionOptions("browser-connection-id"));

        // Act
        AITool tool = FoundryAITool.CreateBrowserAutomationTool(options);

        // Assert
        var responseTool = Assert.IsAssignableFrom<ResponseTool>(tool.GetService(typeof(ResponseTool)));
        var browserAutomationTool = Assert.IsType<BrowserAutomationTool>(responseTool);
        Assert.Same(options, browserAutomationTool.BrowserAutomation);
    }

    [Fact]
    public void CreateBrowserAutomationTool_SerializesAsGaBrowserAutomationTool()
    {
        // Arrange
        var options = new BrowserAutomationToolOptions(new BrowserAutomationToolConnectionOptions("browser-connection-id"));

        // Act
        AITool tool = FoundryAITool.CreateBrowserAutomationTool(options);

        // Assert
        var responseTool = Assert.IsAssignableFrom<ResponseTool>(tool.GetService(typeof(ResponseTool)));
        using JsonDocument json = JsonDocument.Parse(ModelReaderWriter.Write(responseTool, ModelReaderWriterOptions.Json).ToString());
        Assert.Equal("browser_automation", json.RootElement.GetProperty("type").GetString());
        Assert.Equal(
            "browser-connection-id",
            json.RootElement.GetProperty("browser_automation").GetProperty("connection").GetProperty("project_connection_id").GetString());
        Assert.Equal(["browser_automation", "type"], json.RootElement.EnumerateObject().Select(property => property.Name).OrderBy(name => name, StringComparer.Ordinal));
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
            toolCallApprovalPolicy: new McpToolCallApprovalPolicy(DefaultMcpToolCallApprovalPolicy.AlwaysRequireApproval));

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
