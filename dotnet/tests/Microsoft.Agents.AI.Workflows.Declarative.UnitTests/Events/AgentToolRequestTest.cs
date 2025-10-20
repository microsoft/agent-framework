// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Base class for event tests.
/// </summary>
public sealed class AgentToolRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        AgentToolRequest copy =
            VerifyEventSerialization(
                new AgentToolRequest(
                    "agent",
                    [
                        new FunctionCallContent("call1", "result1"),
                        new FunctionCallContent("call2", "result2", new Dictionary<string, object?>() { { "name", "Clam Chowder" } })
                    ]));
        Assert.Equal("agent", copy.AgentName);
    }
}
