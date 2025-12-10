// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

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
        ExternalInputRequest source = new(new AgentRunResponse(new ChatMessage(ChatRole.User, "Wassup?")));

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
            new(new AgentRunResponse(
                    new ChatMessage(
                        ChatRole.Assistant,
                        [
                            new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")),
                            new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")),
                            new FunctionCallContent("call3", "myfunc"),
                            new TextContent("Heya"),
                        ])));

        // Act
        ExternalInputRequest copy = VerifyEventSerialization(source);

        // Assert
        ChatMessage messageCopy = Assert.Single(source.AgentResponse.Messages);
        Assert.Equal(messageCopy.Contents.Count, copy.AgentResponse.Messages[0].Contents.Count);

        McpServerToolApprovalRequestContent mcpRequest = AssertContent<McpServerToolApprovalRequestContent>(messageCopy);
        Assert.Equal("call1", mcpRequest.Id);

        FunctionApprovalRequestContent functionRequest = AssertContent<FunctionApprovalRequestContent>(messageCopy);
        Assert.Equal("call2", functionRequest.Id);

        FunctionCallContent functionCall = AssertContent<FunctionCallContent>(messageCopy);
        Assert.Equal("call3", functionCall.CallId);

        TextContent textContent = AssertContent<TextContent>(messageCopy);
        Assert.Equal("Heya", textContent.Text);
    }
}
