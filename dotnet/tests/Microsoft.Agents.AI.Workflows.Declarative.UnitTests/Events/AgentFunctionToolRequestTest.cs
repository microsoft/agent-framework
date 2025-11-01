// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="AgentFunctionToolRequest"/> class
/// </summary>
public sealed class AgentFunctionToolRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationEmpty()
    {
        // Arrange & Act
        AgentFunctionToolRequest copy = VerifyEventSerialization(new AgentFunctionToolRequest("testagent", []));

        // Assert
        Assert.Equal("testagent", copy.AgentName);
        Assert.Empty(copy.FunctionCalls);
    }

    [Fact]
    public void VerifySerializationWithRequests()
    {
        // Arrange & Act
        AgentFunctionToolRequest copy =
            VerifyEventSerialization(
                new AgentFunctionToolRequest(
                    "agent",
                    [
                        new FunctionCallContent("call1", "result1"),
                        new FunctionCallContent("call2", "result2", new Dictionary<string, object?>() { { "name", "Clam Chowder" } }),
                    ]));

        // Assert
        Assert.Equal("agent", copy.AgentName);
        Assert.Equal(2, copy.FunctionCalls.Count);
        Assert.IsType<FunctionCallContent>(copy.FunctionCalls[0]);
        Assert.Null(copy.FunctionCalls[0].Arguments);
        Assert.IsType<FunctionCallContent>(copy.FunctionCalls[1]);
        Assert.NotNull(copy.FunctionCalls[1].Arguments);
        Assert.NotEmpty(copy.FunctionCalls[1].Arguments!);
    }
}
