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
        ExternalInputRequest source = new(new ChatMessage(ChatRole.User, "Wassup?"));

        // Act
        ExternalInputRequest copy = VerifyEventSerialization(source);

        // Assert
        AssertMessage(source.Message, copy.Message);
    }

    [Fact]
    public void VerifySerializationWithRequests()
    {
        // Arrange
        ExternalInputRequest source =
            new(new ChatMessage(ChatRole.Assistant,
                [
                    new McpServerToolApprovalRequestContent("call1", new McpServerToolCallContent("call1", "testmcp", "server-name")),
                    new FunctionApprovalRequestContent("call2", new FunctionCallContent("call2", "result1")),
                    // %%% FUNCTION CALL
                    // %%% RAW REPRESENTATION ONLY
                ]));

        // Act
        ExternalInputRequest copy = VerifyEventSerialization(source);

        // Assert
        Assert.Equal(source.Message.Contents.Count, copy.Message.Contents.Count);

        McpServerToolApprovalRequestContent mcpRequest = AssertContent<McpServerToolApprovalRequestContent>(copy);
        Assert.Equal("call1", mcpRequest.Id);

        FunctionApprovalRequestContent functionRequest = AssertContent<FunctionApprovalRequestContent>(copy);
        Assert.Equal("call2", functionRequest.Id);
    }

    private static TContent AssertContent<TContent>(ExternalInputRequest request) where TContent : AIContent =>
        AssertContent<TContent>(request.Message);
}
