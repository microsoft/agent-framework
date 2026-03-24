// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="ExternalInputRequest"/> class
/// </summary>
public sealed class ExternalInputRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationWithText()
    {
        // Arrange
        ExternalInputRequest source = new(new AgentResponse(new ChatMessage(ChatRole.User, "Wassup?")));

        // Act
        ExternalInputRequest copy = VerifyEventSerialization(source);

        // Assert
        ChatMessage messageCopy = Assert.Single(source.AgentResponse.Messages);
        AssertMessage(messageCopy, copy.AgentResponse.Messages[0]);
    }

    [Fact]
    public void VerifySerializationWithRequests()
    {
        // Arrange
        ExternalInputRequest source =
            new(new AgentResponse(
                    new ChatMessage(
                        ChatRole.Assistant,
                        [
                            new ToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")),
                            new ToolApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")),
                            new FunctionCallContent("call3", "myfunc"),
                            new TextContent("Heya"),
                        ])));

        // Act
        ExternalInputRequest copy = VerifyEventSerialization(source);

        // Assert
        ChatMessage messageCopy = Assert.Single(source.AgentResponse.Messages);
        Assert.Equal(messageCopy.Contents.Count, copy.AgentResponse.Messages[0].Contents.Count);

        List<ToolApprovalRequestContent> approvalRequests = messageCopy.Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Equal(2, approvalRequests.Count);

        ToolApprovalRequestContent mcpRequest = approvalRequests[0];
        Assert.Equal("call1", mcpRequest.RequestId);

        ToolApprovalRequestContent functionRequest = approvalRequests[1];
        Assert.Equal("call2", functionRequest.RequestId);

        FunctionCallContent functionCall = AssertContent<FunctionCallContent>(messageCopy);
        Assert.Equal("call3", functionCall.CallId);

        TextContent textContent = AssertContent<TextContent>(messageCopy);
        Assert.Equal("Heya", textContent.Text);
    }
}
