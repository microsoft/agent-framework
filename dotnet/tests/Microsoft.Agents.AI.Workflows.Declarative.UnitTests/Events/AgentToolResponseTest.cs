// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Base class for event tests.
/// </summary>
public sealed class AgentToolResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        AgentToolResponse copy =
            VerifyEventSerialization(
                new AgentToolResponse(
                    "agent",
                    [
                        new FunctionResultContent("call1", "result1"),
                        new FunctionResultContent("call2", "result2")
                    ]));
        Assert.Equal("agent", copy.AgentName);
    }
}
