// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

public class FoundryAIToolTests
{
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
