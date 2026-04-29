// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotClientExtensions"/> class.
/// </summary>
public sealed class CopilotClientExtensionsTests
{
    private static readonly PermissionRequestHandler s_testPermissionHandler = (_, _) => Task.FromResult(new PermissionRequestResult { Kind = PermissionRequestResultKind.Approved });

    [Fact]
    public void AsAIAgent_WithAllParameters_ReturnsGitHubCopilotAgentWithSpecifiedProperties()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        const string TestId = "test-agent-id";
        const string TestName = "Test Agent";
        const string TestDescription = "This is a test agent description";

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: false, id: TestId, name: TestName, description: TestDescription, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithMinimalParameters_ReturnsGitHubCopilotAgent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent(sessionConfig: null);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithNullClient_ThrowsArgumentNullException()
    {
        // Arrange
        CopilotClient? copilotClient = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => copilotClient!.AsAIAgent(sessionConfig: null));
    }

    [Fact]
    public void AsAIAgent_WithOwnsClient_ReturnsAgentThatOwnsClient()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: true, id: null, name: null, description: null, tools: null, instructions: null, onPermissionRequest: s_testPermissionHandler);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithTools_ReturnsAgentWithTools()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        List<AITool> tools = [AIFunctionFactory.Create(() => "test", "TestFunc", "Test function")];

        // Act
        var agent = copilotClient.AsAIAgent(ownsClient: false, id: null, name: null, description: null, tools: tools, instructions: null, onPermissionRequest: s_testPermissionHandler);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void AsAIAgent_WithSessionConfig_ReturnsAgent()
    {
        // Arrange
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        var sessionConfig = new SessionConfig { OnPermissionRequest = s_testPermissionHandler };

        // Act
        var agent = copilotClient.AsAIAgent(sessionConfig: sessionConfig);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<GitHubCopilotAgent>(agent);
    }

    [Fact]
    public void OldAsAIAgent_WithoutPermissionHandler_IsMarkedObsoleteWithError()
    {
        // The old extension overload (tools/instructions without onPermissionRequest) should be
        // marked with [Obsolete(error: true)].
        var methods = typeof(CopilotClientExtensions).GetMethods()
            .Where(m => m.Name == "AsAIAgent" && m.GetParameters().Any(p => p.Name == "tools") && !m.GetParameters().Any(p => p.Name == "onPermissionRequest"))
            .ToArray();

        Assert.Single(methods);
        var obsoleteAttr = methods[0].GetCustomAttributes(typeof(ObsoleteAttribute), false);
        Assert.Single(obsoleteAttr);
        var attr = (ObsoleteAttribute)obsoleteAttr[0];
        Assert.True(attr.IsError);
        Assert.Contains("OnPermissionRequest", attr.Message);
    }
}
