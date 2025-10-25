// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="UserInputRequest"/> class
/// </summary>
public sealed class UserInputRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationEmpty()
    {
        // Arrange & Act
        UserInputRequest copy = VerifyEventSerialization(new UserInputRequest("test agent", []));

        // Assert
        Assert.Equal("test agent", copy.AgentName);
        Assert.Empty(copy.InputRequests);
    }

    [Fact]
    public void VerifySerializationWithRequests()
    {
        // Arrange & Act
        UserInputRequest copy =
            VerifyEventSerialization(
                new UserInputRequest(
                    "agent",
                    [
                        new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")),
                        new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")),
                    ]));

        // Assert
        Assert.Equal("agent", copy.AgentName);
        Assert.Equal(2, copy.InputRequests.Count);
        McpServerToolApprovalRequestContent mcpRequest = Assert.IsType<McpServerToolApprovalRequestContent>(copy.InputRequests[0]);
        Assert.Equal("call1", mcpRequest.Id);
        FunctionApprovalRequestContent functionRequest = Assert.IsType<FunctionApprovalRequestContent>(copy.InputRequests[1]);
        Assert.Equal("call2", functionRequest.Id);
    }
}
