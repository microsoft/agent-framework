// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Abstractions;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Tests workflow executor lifecycle mapping to AG-UI step events.
/// </summary>
public sealed class WorkflowAGUIExtensionsTests
{
    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorInvokedToStepStartedAsync()
    {
        // Arrange
        AgentResponseUpdate update = CreateUpdate(new ExecutorInvokedEvent("reviewer", "input"));

        // Act
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.RawRepresentation.Should().BeOfType<StepStartedEvent>()
            .Which.StepName.Should().Be("reviewer");
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorCompletedToStepFinishedAsync()
    {
        // Arrange
        AgentResponseUpdate update = CreateUpdate(new ExecutorCompletedEvent("reviewer", "result"));

        // Act
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.RawRepresentation.Should().BeOfType<StepFinishedEvent>()
            .Which.StepName.Should().Be("reviewer");
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorFailedAndPreservesErrorAsync()
    {
        // Arrange
        ErrorContent error = new("An error occurred while executing the workflow.");
        AgentResponseUpdate update = CreateUpdate(
            new ExecutorFailedEvent("reviewer", new InvalidOperationException("internal")),
            error);

        // Act
        List<ChatResponseUpdate> results = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .ToListAsync();

        // Assert
        results.Should().HaveCount(2);
        results[0].RawRepresentation.Should().BeOfType<StepFinishedEvent>()
            .Which.StepName.Should().Be("reviewer");
        results[0].Contents.Should().BeEmpty();
        results[1].RawRepresentation.Should().BeSameAs(update);
        results[1].Contents.Should().ContainSingle().Which.Should().BeSameAs(error);
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_ForwardsOtherUpdatesUnchangedAsync()
    {
        // Arrange
        WorkflowStartedEvent workflowStarted = new("workflow");
        TextContent text = new("hello");
        AgentResponseUpdate update = CreateUpdate(workflowStarted, text);

        // Act
        ChatResponseUpdate convertedUpdate = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .SingleAsync();
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(convertedUpdate)
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.Should().BeSameAs(convertedUpdate);
        result.RawRepresentation.Should().BeSameAs(update);
        result.Contents.Should().ContainSingle().Which.Should().BeSameAs(text);
    }

    private static AgentResponseUpdate CreateUpdate(object raw, params AIContent[] contents)
        => new(ChatRole.Assistant, contents)
        {
            AuthorName = "author",
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = "message",
            RawRepresentation = raw,
            ResponseId = "response",
        };

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(
        AgentResponseUpdate update)
    {
        await Task.Yield();
        yield return update;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableAsync(
        ChatResponseUpdate update)
    {
        await Task.Yield();
        yield return update;
    }
}
