// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="UserInputResponse"/> class
/// </summary>
public sealed class UserInputResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationEmpty()
    {
        // Arrange & Act
        UserInputResponse copy = VerifyEventSerialization(new UserInputResponse("testagent", []));

        // Assert
        Assert.Equal("testagent", copy.AgentName);
        Assert.Empty(copy.InputResponses);
    }

    [Fact]
    public void VerifySerializationWithResponses()
    {
        // Arrange & Act
        UserInputResponse copy =
            VerifyEventSerialization(
                new UserInputResponse(
                    "agent",
                    [
                        new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")).CreateResponse(approved: true),
                        new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")).CreateResponse(approved: true),
                    ]));

        // Assert
        Assert.Equal("agent", copy.AgentName);
        Assert.Equal(2, copy.InputResponses.Count);
        McpServerToolApprovalResponseContent mcpResponse = Assert.IsType<McpServerToolApprovalResponseContent>(copy.InputResponses[0]);
        Assert.Equal("call1", mcpResponse.Id);
        FunctionApprovalResponseContent functionResponse = Assert.IsType<FunctionApprovalResponseContent>(copy.InputResponses[1]);
        Assert.Equal("call2", functionResponse.Id);
    }
}
