// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Regression tests for a failing workflow used as an agent: the emitted update carries a
/// <see cref="WorkflowErrorEvent"/> as its raw representation, whose data is the original
/// <see cref="Exception"/>. Streaming that update must not try to JSON-serialize the exception,
/// which fails on <c>Exception.TargetSite</c> and hides the actual workflow failure.
/// </summary>
public sealed class WorkflowErrorEventStreamingTests
{
    [Fact]
    public async Task WorkflowErrorEvent_IsStreamedWithoutSerializationFailureAsync()
    {
        // Arrange: the update a failing workflow-as-agent produces.
        const string ErrorMessage = "Executor 'AggregatorExecutor' cannot send messages of type 'RawAggregate'.";
        var update = new AgentResponseUpdate(ChatRole.Assistant, [new ErrorContent(ErrorMessage)])
        {
            RawRepresentation = new WorkflowErrorEvent(Thrown(ErrorMessage))
        };

        var request = new CreateResponse { Input = "Hello", Stream = true };
        var context = new AgentInvocationContext(new IdGenerator("resp_1", "conv_1"));

        // Act
        List<StreamingResponseEvent> events = [];
        await foreach (var evt in ToAsyncEnumerableAsync(update).ToStreamingResponseAsync(request, context))
        {
            events.Add(evt);
        }

        // Assert: the workflow event is streamed and carries the real failure message.
        var workflowEvent = Assert.Single(events.OfType<StreamingWorkflowEventComplete>());
        Assert.NotNull(workflowEvent.Data);
        JsonElement data = workflowEvent.Data.Value;
        Assert.Equal(nameof(WorkflowErrorEvent), data.GetProperty("event_type").GetString());
        Assert.Equal(ErrorMessage, data.GetProperty("data").GetString());
    }

    /// <summary>Returns an actually-thrown exception, so <c>TargetSite</c> is populated.</summary>
    private static InvalidOperationException Thrown(string message)
    {
        try
        {
            throw new InvalidOperationException(message);
        }
        catch (InvalidOperationException ex)
        {
            return ex;
        }
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(params AgentResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }
}
