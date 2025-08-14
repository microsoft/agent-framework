// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests <see cref="DeclarativeWorkflowEvent"/> and subclasses.
/// </summary>
public sealed class DeclarativeWorkflowEventTest(ITestOutputHelper output) : WorkflowTest(output)
{
    /// <summary>
    /// Tests the <see cref="DeclarativeWorkflowMessageEvent"/> class.
    /// </summary>
    [Fact]
    public void DeclarativeWorkflowMessageEvent()
    {
        ChatMessage testMessage = new(ChatRole.Assistant, "test message");
        DeclarativeWorkflowMessageEvent workflowEvent = new(testMessage);
        Assert.Equal(testMessage, workflowEvent.Data);
        Assert.Null(workflowEvent.Usage);
    }

    /// <summary>
    /// Tests the <see cref="DeclarativeWorkflowStreamEvent"/> class.
    /// </summary>
    [Fact]
    public void DeclarativeWorkflowStreamEvent()
    {
        ChatResponseUpdate testUpdate = new(ChatRole.Assistant, "test message");
        DeclarativeWorkflowStreamEvent workflowEvent = new(testUpdate);
        Assert.Equal(testUpdate, workflowEvent.Data);
    }
}
