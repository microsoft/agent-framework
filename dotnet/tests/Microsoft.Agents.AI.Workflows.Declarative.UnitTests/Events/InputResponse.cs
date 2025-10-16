// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Base class for event tests.
/// </summary>
public sealed class InputResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        InputResponse copy = VerifyEventSerialization(new InputResponse("test response"));
        Assert.Equal("test response", copy.Value);
    }
}
