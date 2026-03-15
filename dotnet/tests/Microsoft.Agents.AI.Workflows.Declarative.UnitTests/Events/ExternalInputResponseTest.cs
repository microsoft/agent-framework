// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;

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
        ChatMessage messageCopy = Assert.Single(source.Messages);
        AssertMessage(messageCopy, copy.Messages[0]);
    }

    [Fact]
    public void VerifySerializationWithResponses()
    {
        // Arrange
        ExternalInputResponse source =
            new(new ChatMessage(
                ChatRole.Assistant,
                [
                    new ToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")).CreateResponse(approved: true),
                    new ToolApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")).CreateResponse(approved: true),
                    new FunctionResultContent("call3", 33),
                    new TextContent("Heya"),
                ]));

        // Act
        ExternalInputResponse copy = VerifyEventSerialization(source);

        // Assert
        ChatMessage responseMessage = Assert.Single(source.Messages);
        Assert.Equal(responseMessage.Contents.Count, copy.Messages[0].Contents.Count);

        ToolApprovalResponseContent[] approvalResponses = responseMessage.Contents.OfType<ToolApprovalResponseContent>().ToArray();
        Assert.Equal(2, approvalResponses.Length);
        Assert.Equal("call1", approvalResponses[0].RequestId);
        Assert.Equal("call2", approvalResponses[1].RequestId);

        FunctionResultContent functionResult = AssertContent<FunctionResultContent>(responseMessage);
        Assert.Equal("call3", functionResult.CallId);

        TextContent textContent = AssertContent<TextContent>(responseMessage);
        Assert.Equal("Heya", textContent.Text);
    }
}
