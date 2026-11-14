// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests the request / response flow of a <c>Question</c> action defined in a declarative workflow,
/// resuming from a JSON checkpoint for each response.
/// </summary>
public sealed class QuestionWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private const string ClosedListWorkflow = "QuestionClosedList.yaml";

    [Theory]
    [InlineData("red", "option-1")]
    [InlineData("Crimson", "option-1")]
    [InlineData(" YELLO ", "option-2")]
    [InlineData("option-2", "option-2")]
    public async Task QuestionClosedListCapturesSelectedItemAsync(string response, string expectedItemId)
    {
        // Act
        List<WorkflowEvent> events = await this.RunWorkflowAsync(ClosedListWorkflow, response);

        // Assert
        Assert.Single(events.OfType<RequestInfoEvent>());
        Assert.DoesNotContain(events.OfType<MessageActivityEvent>(), e => e.Message.Contains("Please pick one", StringComparison.Ordinal));
        AssertMessage(events, $"Selected: \"{expectedItemId}\"");
    }

    [Fact]
    public async Task QuestionClosedListRepromptsOnUnknownItemAsync()
    {
        // Act
        List<WorkflowEvent> events = await this.RunWorkflowAsync(ClosedListWorkflow, "purple", "red");

        // Assert
        Assert.Equal(2, events.OfType<RequestInfoEvent>().Count());
        AssertMessage(events, "Please pick one of the listed colors.");
        Assert.DoesNotContain(events.OfType<MessageActivityEvent>(), e => e.Message.Contains("using the default", StringComparison.Ordinal));
        AssertMessage(events, "Selected: \"option-1\"");
    }

    [Fact]
    public async Task QuestionClosedListAssignsDefaultAfterRepeatCountAsync()
    {
        // Act
        List<WorkflowEvent> events = await this.RunWorkflowAsync(ClosedListWorkflow, "purple", "blue");

        // Assert
        Assert.Equal(2, events.OfType<RequestInfoEvent>().Count());
        AssertMessage(events, "No valid color selected, using the default.");
        AssertMessage(events, "Selected: \"option-2\"");
    }

    private static void AssertMessage(List<WorkflowEvent> events, string message) =>
        Assert.Contains(events.OfType<MessageActivityEvent>(), e => string.Equals(e.Message.Trim(), message, StringComparison.Ordinal));

    private async Task<List<WorkflowEvent>> RunWorkflowAsync(string workflowFile, params string[] responses)
    {
        DirectoryInfo checkpointFolder = Directory.CreateDirectory(Path.Combine(Path.GetTempPath(), $"af-question-{Guid.NewGuid():N}"));
        try
        {
            using FileSystemJsonCheckpointStore store = new(checkpointFolder);
            CheckpointManager checkpointManager = CheckpointManager.CreateJson(store, DeclarativeWorkflowJsonOptions.Default);

            List<WorkflowEvent> events = [];
            (RequestInfoEvent? request, CheckpointInfo? checkpoint) = await this.WatchAsync(
                await InProcessExecution.RunStreamingAsync(this.CreateWorkflow(workflowFile), "start", checkpointManager),
                response: null,
                events);

            foreach (string responseText in responses)
            {
                Assert.NotNull(request);
                Assert.NotNull(checkpoint);

                // Resume a freshly built workflow from the checkpoint to exercise pause / resume.
                ExternalResponse response = request.Request.CreateResponse(new ExternalInputResponse(new ChatMessage(ChatRole.User, responseText)));
                (request, checkpoint) = await this.WatchAsync(
                    await InProcessExecution.ResumeStreamingAsync(this.CreateWorkflow(workflowFile), checkpoint, checkpointManager),
                    response,
                    events);
            }

            Assert.Null(request);
            return events;
        }
        finally
        {
            checkpointFolder.Delete(recursive: true);
        }
    }

    private async Task<(RequestInfoEvent? Request, CheckpointInfo? Checkpoint)> WatchAsync(StreamingRun run, ExternalResponse? response, List<WorkflowEvent> events)
    {
        await using StreamingRun _ = run;

        if (response is not null)
        {
            await run.SendResponseAsync(response);
        }

        RequestInfoEvent? request = null;
        CheckpointInfo? checkpoint = null;
        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync(blockOnPendingRequest: false))
        {
            switch (workflowEvent)
            {
                case RequestInfoEvent requestEvent when requestEvent.Request.RequestId != response?.RequestId:
                    ExternalInputRequest inputRequest = Assert.IsType<ExternalInputRequest>(requestEvent.Request.Data.As<ExternalInputRequest>());
                    this.Output.WriteLine($"REQUEST: {inputRequest.AgentResponse.Text}");
                    request = requestEvent;
                    events.Add(workflowEvent);
                    break;

                case SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } completedCheckpoint }:
                    checkpoint = completedCheckpoint;
                    break;

                case MessageActivityEvent activityEvent:
                    this.Output.WriteLine($"ACTIVITY: {activityEvent.Message}");
                    events.Add(workflowEvent);
                    break;

                case WorkflowErrorEvent errorEvent:
                    throw errorEvent.Data as Exception ?? new XunitException("Unexpected failure...");
            }
        }

        return (request, checkpoint);
    }

    private Workflow CreateWorkflow(string workflowFile)
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowFile));
        DeclarativeWorkflowOptions options = new(new MockAgentProvider().Object) { LoggerFactory = this.Output };
        return DeclarativeWorkflowBuilder.Build<string>(yamlReader, options);
    }
}
