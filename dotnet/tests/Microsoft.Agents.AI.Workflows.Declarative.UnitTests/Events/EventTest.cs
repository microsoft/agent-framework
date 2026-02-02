// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Base class for event tests.
/// </summary>
public abstract class EventTest(ITestOutputHelper output) : WorkflowTest(output)
{
    protected static TEvent VerifyEventSerialization<TEvent>(TEvent source)
    {
        string? text = JsonSerializer.Serialize(source, AIJsonUtilities.DefaultOptions);
        Assert.NotNull(text);
        TEvent? copy = JsonSerializer.Deserialize<TEvent>(text, AIJsonUtilities.DefaultOptions);
        Assert.NotNull(copy);
        return copy;
    }

    protected static void AssertMessage(ChatMessage source, ChatMessage copy)
    {
        Assert.Equal(source.Role, copy.Role);
        Assert.Equal(source.Text, copy.Text);
        Assert.Equal(source.Contents.Count, copy.Contents.Count);
    }

    protected static TContent AssertContent<TContent>(ChatMessage message) where TContent : AIContent
    {
        TContent[] contents = message.Contents.OfType<TContent>().ToArray();
        return Assert.Single(contents);
    }
}
