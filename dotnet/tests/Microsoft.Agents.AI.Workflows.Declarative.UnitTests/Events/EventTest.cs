// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Base class for event tests.
/// </summary>
public abstract class EventTest(ITestOutputHelper output) : WorkflowTest(output)
{
    protected static TEvent VerifyEventSerialization<TEvent>(TEvent source)
    {
        string? text = JsonSerializer.Serialize(source);
        Assert.NotNull(text);
        TEvent? copy = JsonSerializer.Deserialize<TEvent>(text);
        Assert.NotNull(copy);
        return copy;
    }
}
