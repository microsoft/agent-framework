// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="AgentFunctionToolResponse"/> class
/// </summary>
public sealed class AgentFunctionToolResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationEmpty()
    {
        // Arrange & Act
        AgentFunctionToolResponse copy = VerifyEventSerialization(new AgentFunctionToolResponse("testagent", []));

        // Assert
        Assert.Equal("testagent", copy.AgentName);
        Assert.Empty(copy.FunctionResults);
    }

    [Fact]
    public void VerifySerializationWithResults()
    {
        // Arrange & Act
        AgentFunctionToolResponse copy =
            VerifyEventSerialization(
                new AgentFunctionToolResponse(
                    "agent",
                    [
                        new FunctionResultContent("call1", "result1"),
                        new FunctionResultContent("call2", "result2"),
                    ]));

        // Assert
        Assert.Equal("agent", copy.AgentName);
        Assert.Equal(2, copy.FunctionResults.Count);
        Assert.IsType<FunctionResultContent>(copy.FunctionResults[0]);
        Assert.Equal("call1", copy.FunctionResults[0].CallId);
        Assert.IsType<FunctionResultContent>(copy.FunctionResults[1]);
        Assert.Equal("call2", copy.FunctionResults[1].CallId);
    }
}
