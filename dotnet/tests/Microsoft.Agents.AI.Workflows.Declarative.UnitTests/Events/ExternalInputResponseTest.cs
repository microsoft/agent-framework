// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="ExternalInputResponse"/> class
/// </summary>
public sealed class ExternalInputResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationEmpty()
    {
        // Arrange
        ExternalInputResponse source = new(new ChatMessage(ChatRole.User, "Wassup?"));

        // Act
        ExternalInputResponse copy = VerifyEventSerialization(source);

        // Assert
        AssertMessage(source.Message, copy.Message);
    }

    [Fact]
    public void VerifySerializationWithResponses()
    {
        // Arrange
        ExternalInputResponse source =
            new(new ChatMessage(
                ChatRole.Assistant,
                [
                    new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")).CreateResponse(approved: true),
                    new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")).CreateResponse(approved: true),
                    new FunctionResultContent("call3", 33),
                    new TextContent("Heya"),
                ]));

        // Act
        ExternalInputResponse copy = VerifyEventSerialization(source);

        // Assert
        Assert.Equal(source.Message.Contents.Count, copy.Message.Contents.Count);

        McpServerToolApprovalResponseContent mcpApproval = AssertContent<McpServerToolApprovalResponseContent>(copy);
        Assert.Equal("call1", mcpApproval.Id);

        FunctionApprovalResponseContent functionApproval = AssertContent<FunctionApprovalResponseContent>(copy);
        Assert.Equal("call2", functionApproval.Id);

        FunctionResultContent functionResult = AssertContent<FunctionResultContent>(copy);
        Assert.Equal("call3", functionResult.CallId);

        TextContent textContent = AssertContent<TextContent>(copy);
        Assert.Equal("Heya", textContent.Text);
    }

    private static TContent AssertContent<TContent>(ExternalInputResponse response) where TContent : AIContent =>
        AssertContent<TContent>(response.Message);
}
