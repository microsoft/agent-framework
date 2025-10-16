// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Base class for event tests.
/// </summary>
public sealed class InputRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        InputRequest copy = VerifyEventSerialization(new InputRequest("wassup"));
        Assert.Equal("wassup", copy.Prompt);
    }
}
