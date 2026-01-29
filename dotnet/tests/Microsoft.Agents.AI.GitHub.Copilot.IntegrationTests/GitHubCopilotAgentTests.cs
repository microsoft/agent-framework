// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.IntegrationTests;

public class GitHubCopilotAgentTests
{
    private const string SkipReason = "Integration tests require GitHub Copilot CLI installed. For local execution only.";

    private static Task<PermissionRequestResult> OnPermissionRequestAsync(PermissionRequest request, PermissionInvocation invocation)
        => Task.FromResult(new PermissionRequestResult { Kind = "approved" });

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithSimplePrompt_ReturnsResponseAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        await using GitHubCopilotAgent agent = new(client, sessionConfig: null);

        // Act
        AgentResponse response = await agent.RunAsync("What is 2 + 2? Answer with just the number.");

        // Assert
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        Assert.Contains("4", response.Text);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunStreamingAsync_WithSimplePrompt_ReturnsUpdatesAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        await using GitHubCopilotAgent agent = new(client, sessionConfig: null);

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("What is 2 + 2? Answer with just the number."))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        string fullText = string.Join("", updates.Select(u => u.Text));
        Assert.Contains("4", fullText);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithFunctionTool_InvokesToolAsync()
    {
        // Arrange
        bool toolInvoked = false;

        AIFunction weatherTool = AIFunctionFactory.Create((string location) =>
        {
            toolInvoked = true;
            return $"The weather in {location} is sunny with a high of 25C.";
        }, "GetWeather", "Get the weather for a given location.");

        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        await using GitHubCopilotAgent agent = new(
            client,
            tools: [weatherTool],
            instructions: "You are a helpful weather agent. Use the GetWeather tool to answer weather questions.");

        // Act
        AgentResponse response = await agent.RunAsync("What's the weather like in Seattle?");

        // Assert
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        Assert.True(toolInvoked);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithSession_MaintainsContextAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        await using GitHubCopilotAgent agent = new(
            client,
            instructions: "You are a helpful assistant. Keep your answers short.");

        AgentSession session = await agent.GetNewSessionAsync();

        // Act - First turn
        AgentResponse response1 = await agent.RunAsync("My name is Alice.", session);
        Assert.NotNull(response1);

        // Act - Second turn using same session
        AgentResponse response2 = await agent.RunAsync("What is my name?", session);

        // Assert
        Assert.NotNull(response2);
        Assert.Contains("Alice", response2.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithSessionResume_ContinuesConversationAsync()
    {
        // Arrange - First agent instance starts a conversation
        string? sessionId;

        await using CopilotClient client1 = new(new CopilotClientOptions());
        await client1.StartAsync();

        await using GitHubCopilotAgent agent1 = new(
            client1,
            instructions: "You are a helpful assistant. Keep your answers short.");

        AgentSession session1 = await agent1.GetNewSessionAsync();
        await agent1.RunAsync("Remember this number: 42.", session1);

        sessionId = ((GitHubCopilotAgentSession)session1).SessionId;
        Assert.NotNull(sessionId);

        // Act - Second agent instance resumes the session
        await using CopilotClient client2 = new(new CopilotClientOptions());
        await client2.StartAsync();

        await using GitHubCopilotAgent agent2 = new(
            client2,
            instructions: "You are a helpful assistant. Keep your answers short.");

        AgentSession session2 = await agent2.GetNewSessionAsync(sessionId);
        AgentResponse response = await agent2.RunAsync("What number did I ask you to remember?", session2);

        // Assert
        Assert.NotNull(response);
        Assert.Contains("42", response.Text);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithShellPermissions_ExecutesCommandAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        SessionConfig sessionConfig = new()
        {
            OnPermissionRequest = OnPermissionRequestAsync,
        };

        await using GitHubCopilotAgent agent = new(client, sessionConfig);

        // Act
        AgentResponse response = await agent.RunAsync("Run a shell command to print 'hello world'");

        // Assert
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        Assert.Contains("hello", response.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithUrlPermissions_FetchesContentAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        SessionConfig sessionConfig = new()
        {
            OnPermissionRequest = OnPermissionRequestAsync,
        };

        await using GitHubCopilotAgent agent = new(client, sessionConfig);

        // Act
        AgentResponse response = await agent.RunAsync(
            "Fetch https://learn.microsoft.com/agent-framework/tutorials/quick-start and summarize its contents in one sentence");

        // Assert
        Assert.NotNull(response);
        Assert.Contains("Agent Framework", response.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithLocalMcpServer_UsesServerToolsAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        SessionConfig sessionConfig = new()
        {
            OnPermissionRequest = OnPermissionRequestAsync,
            McpServers = new Dictionary<string, object>
            {
                ["filesystem"] = new McpLocalServerConfig
                {
                    Type = "stdio",
                    Command = "npx",
                    Args = ["-y", "@modelcontextprotocol/server-filesystem", "."],
                    Tools = ["*"],
                },
            },
        };

        await using GitHubCopilotAgent agent = new(client, sessionConfig);

        // Act
        AgentResponse response = await agent.RunAsync("List the files in the current directory");

        // Assert
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        Assert.NotEmpty(response.Text);
    }

    [Fact(Skip = SkipReason)]
    public async Task RunAsync_WithRemoteMcpServer_UsesServerToolsAsync()
    {
        // Arrange
        await using CopilotClient client = new(new CopilotClientOptions());
        await client.StartAsync();

        SessionConfig sessionConfig = new()
        {
            OnPermissionRequest = OnPermissionRequestAsync,
            McpServers = new Dictionary<string, object>
            {
                ["microsoft-learn"] = new McpRemoteServerConfig
                {
                    Type = "http",
                    Url = "https://learn.microsoft.com/api/mcp",
                    Tools = ["*"],
                },
            },
        };

        await using GitHubCopilotAgent agent = new(client, sessionConfig);

        // Act
        AgentResponse response = await agent.RunAsync("Search Microsoft Learn for 'Azure Functions' and summarize the top result");

        // Assert
        Assert.NotNull(response);
        Assert.Contains("Azure Functions", response.Text, StringComparison.OrdinalIgnoreCase);
    }
}
