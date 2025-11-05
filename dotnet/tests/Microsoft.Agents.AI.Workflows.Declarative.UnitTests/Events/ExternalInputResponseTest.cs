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
            new(new ChatMessage(ChatRole.Assistant,
                [
                    new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")).CreateResponse(approved: true),
                    new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")).CreateResponse(approved: true),
                    // %%% FUNCTION CALL
                    // %%% RAW REPRESENTATION ONLY
                ]));

        // Act
        ExternalInputResponse copy = VerifyEventSerialization(source);

        // Assert
        Assert.Equal(source.Message.Contents.Count, copy.Message.Contents.Count);

        McpServerToolApprovalResponseContent mcpRequest = AssertContent<McpServerToolApprovalResponseContent>(copy);
        Assert.Equal("call1", mcpRequest.Id);

        FunctionApprovalResponseContent functionRequest = AssertContent<FunctionApprovalResponseContent>(copy);
        Assert.Equal("call2", functionRequest.Id);
    }

    private static TContent AssertContent<TContent>(ExternalInputResponse response) where TContent : AIContent =>
        AssertContent<TContent>(response.Message);
}
