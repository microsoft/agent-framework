// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Verifies that an agent which reports a failure aborts the workflow instead of silently
/// advancing to the next action and finalizing as a successful, empty response.
/// </summary>
public sealed class InvokeAgentFailureTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private const string FollowupWorkflow = "AgentFailureFollowup.yaml";
    private const string NoAutoSendWorkflow = "AgentFailureNoAutoSend.yaml";
    private const string DownstreamActionId = "after_agent";
    private const string AgentActionId = "invoke_agent";

    /// <summary>
    /// Matches the agent name declared by the test workflow YAML.
    /// </summary>
    private const string AgentName = "TestAgent";

    /// <summary>
    /// A response carrying <see cref="ErrorContent"/> fails the action. Refusals surface through the
    /// same content type, so they are covered by the same rule.
    /// </summary>
    [Theory]
    [InlineData("Agent run failed.", "server_error")]
    [InlineData("I cannot help with that.", "Refusal")]
    public async Task ErrorContentResponseFailsWorkflowAsync(string message, string errorCode)
    {
        // Arrange
        List<AgentResponseUpdate> updates = [ErrorUpdate(message, errorCode)];

        // Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(FollowupWorkflow, updates);

        // Assert
        Assert.Contains(events, e => e is ExecutorFailedEvent);
        this.AssertNotExecuted(events, DownstreamActionId);
    }

    /// <summary>
    /// The failure is detected on the aggregated response, so it is independent of whether the
    /// response was forwarded as workflow output.
    /// </summary>
    [Fact]
    public async Task ErrorContentResponseFailsWorkflowWhenAutoSendDisabledAsync()
    {
        // Arrange
        List<AgentResponseUpdate> updates = [ErrorUpdate("Agent run failed.", "server_error")];

        // Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(NoAutoSendWorkflow, updates);

        // Assert
        Assert.Contains(events, e => e is ExecutorFailedEvent);

        // Response updates are emitted only on the autoSend path, confirming autoSend is off.
        Assert.DoesNotContain(events, e => e is AgentResponseUpdateEvent);
    }

    /// <summary>
    /// A contentless update is not a failure signal to the engine. Translating a failed Responses
    /// run into <see cref="ErrorContent"/> is the provider's job, so a mocked provider cannot
    /// produce that signal. See <c>AzureAgentProviderFailureTest</c>.
    /// </summary>
    [Fact]
    public async Task ContentlessResponseDoesNotFailWorkflowAsync()
    {
        // Arrange
        List<AgentResponseUpdate> updates = [new(ChatRole.Assistant, []) { ResponseId = "resp_empty" }];

        // Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(FollowupWorkflow, updates);

        // Assert
        Assert.DoesNotContain(events, e => e is ExecutorFailedEvent);
        this.AssertExecuted(events, DownstreamActionId);
    }

    /// <summary>
    /// Control: a transport failure aborts the workflow.
    /// </summary>
    [Fact]
    public async Task ThrownExceptionFailsWorkflowAsync()
    {
        // Arrange & Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(FollowupWorkflow, updates: null, throwOnInvoke: true);

        // Assert
        Assert.Contains(events, e => e is ExecutorFailedEvent);
        this.AssertNotExecuted(events, DownstreamActionId);
    }

    /// <summary>
    /// A successful response still completes the workflow, so the failure rule does not capture
    /// ordinary responses.
    /// </summary>
    [Fact]
    public async Task SuccessfulResponseCompletesWorkflowAsync()
    {
        // Arrange
        List<AgentResponseUpdate> updates = [new(ChatRole.Assistant, [new TextContent("All good.")])];

        // Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(FollowupWorkflow, updates);

        // Assert
        Assert.DoesNotContain(events, e => e is ExecutorFailedEvent);
        this.AssertExecuted(events, AgentActionId);
        this.AssertExecuted(events, DownstreamActionId);
    }

    /// <summary>
    /// A failed run reaching the hosting boundary surfaces an error rather than an empty response.
    /// Exercises both halves of the fix: the failure arrives with no content and must be translated
    /// before the engine can act on it.
    /// </summary>
    [Fact]
    public async Task FailedResponseSurfacesErrorToHostedAgentAsync()
    {
        // Arrange
        List<AgentResponseUpdate> updates =
            await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(
                AgentName,
                AgentUpdateTestHelpers.CreateFailedUpdate("server_error", "Something went wrong."));
        AIAgent hostAgent =
            CreateWorkflow(FollowupWorkflow, updates, throwOnInvoke: false)
                .AsAIAgent(id: "host", name: "host", includeExceptionDetails: true);

        // Act
        AgentResponse response = await hostAgent.RunAsync("Test input message");

        // Assert
        ErrorContent[] errors = [.. response.Messages.SelectMany(message => message.Contents).OfType<ErrorContent>()];
        Assert.NotEmpty(errors);
        Assert.Contains(
            errors,
            error =>
                error.Message.Contains(AgentName, StringComparison.Ordinal) &&
                error.Message.Contains("server_error", StringComparison.Ordinal) &&
                error.Message.Contains("Something went wrong.", StringComparison.Ordinal));
    }

    /// <summary>
    /// The agent's raw error text must not reach the client unless the host opted into exception
    /// detail. The failure is reported either way; only the detail is withheld.
    /// </summary>
    [Fact]
    public async Task FailedResponseIsRedactedFromHostedAgentByDefaultAsync()
    {
        // Arrange
        const string ProviderDetail = "Deployment 'internal-gpt-x' quota exceeded.";
        List<AgentResponseUpdate> updates =
            await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(
                AgentName,
                AgentUpdateTestHelpers.CreateFailedUpdate("server_error", ProviderDetail));
        AIAgent hostAgent =
            CreateWorkflow(FollowupWorkflow, updates, throwOnInvoke: false)
                .AsAIAgent(id: "host", name: "host");

        // Act
        AgentResponse response = await hostAgent.RunAsync("Test input message");

        // Assert
        ErrorContent[] errors = [.. response.Messages.SelectMany(message => message.Contents).OfType<ErrorContent>()];
        Assert.NotEmpty(errors);
        Assert.DoesNotContain(errors, error => error.Message.Contains(ProviderDetail, StringComparison.Ordinal));
        Assert.DoesNotContain(errors, error => error.Message.Contains(AgentName, StringComparison.Ordinal));
    }

    /// <summary>
    /// Raw provider detail must not reach streaming callers either. Updates are forwarded verbatim,
    /// so detail carried in a raw representation would bypass the exception-detail policy even
    /// though the visible content is redacted.
    /// </summary>
    [Fact]
    public async Task FailedResponseIsRedactedFromHostedStreamByDefaultAsync()
    {
        // Arrange
        const string ProviderDetail = "Deployment 'internal-gpt-x' quota exceeded.";
        List<AgentResponseUpdate> updates =
            await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(
                AgentName,
                AgentUpdateTestHelpers.CreateFailedUpdate("server_error", ProviderDetail));
        AIAgent hostAgent =
            CreateWorkflow(FollowupWorkflow, updates, throwOnInvoke: false)
                .AsAIAgent(id: "host", name: "host");

        // Act
        List<AgentResponseUpdate> streamed = [];
        await foreach (AgentResponseUpdate update in hostAgent.RunStreamingAsync("Test input message"))
        {
            streamed.Add(update);
        }

        // Assert - the provider's own failure object never reaches the client.
        Assert.DoesNotContain(
            streamed,
            update => (update.RawRepresentation as ChatResponseUpdate)?.RawRepresentation is StreamingResponseFailedUpdate);
        Assert.DoesNotContain(
            streamed.SelectMany(update => update.Contents).OfType<ErrorContent>(),
            error => error.Message.Contains(ProviderDetail, StringComparison.Ordinal));
    }

    /// <summary>
    /// Both halves composed: a <c>response.failed</c> event arrives contentless, the provider
    /// translates it into <see cref="ErrorContent"/>, and the engine aborts rather than advancing
    /// to the next action.
    /// </summary>
    [Fact]
    public async Task FailedResponseFromProviderFailsWorkflowAsync()
    {
        // Arrange - the provider emits what AzureAgentProvider produces for a failed run.
        List<AgentResponseUpdate> updates =
            await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(
                AgentName,
                AgentUpdateTestHelpers.CreateFailedUpdate("server_error", "Something went wrong."));

        // Act
        WorkflowEvent[] events = await this.RunWorkflowAsync(FollowupWorkflow, updates);

        // Assert
        Assert.Contains(events, e => e is ExecutorFailedEvent);
        this.AssertNotExecuted(events, DownstreamActionId);
    }

    /// <summary>
    /// A failed run that carries no error detail is reported by the provider as a generic
    /// placeholder, and the specific cause follows as its own error. The specific cause must win.
    /// </summary>
    [Fact]
    public async Task SpecificErrorTakesPrecedenceOverGenericFallbackAsync()
    {
        // Arrange - response.failed with a null error, then the follow-up carrying the real cause.
        const string SpecificDetail = "Rate limit exceeded for deployment.";
        List<AgentResponseUpdate> updates =
            await AgentUpdateTestHelpers.ApplyFailureDetectionAsync(
                AgentName,
                AgentUpdateTestHelpers.CreateFailedUpdate(errorCode: null, errorMessage: null));
        updates.Add(ErrorUpdate(SpecificDetail, "rate_limit"));

        AIAgent hostAgent =
            CreateWorkflow(FollowupWorkflow, updates, throwOnInvoke: false)
                .AsAIAgent(id: "host", name: "host", includeExceptionDetails: true);

        // Act
        AgentResponse response = await hostAgent.RunAsync("Test input message");

        // Assert
        ErrorContent[] errors = [.. response.Messages.SelectMany(message => message.Contents).OfType<ErrorContent>()];
        Assert.Contains(errors, error => error.Message.Contains(SpecificDetail, StringComparison.Ordinal));
        Assert.DoesNotContain(errors, error => error.Message.Contains("The agent run failed.", StringComparison.Ordinal));
    }

    private static AgentResponseUpdate ErrorUpdate(string message, string errorCode) =>
        new(ChatRole.Assistant, [new ErrorContent(message) { ErrorCode = errorCode }]) { ResponseId = "resp_error" };

    private void AssertExecuted(IEnumerable<WorkflowEvent> events, string executorId) =>
        Assert.Contains(events.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);

    private void AssertNotExecuted(IEnumerable<WorkflowEvent> events, string executorId) =>
        Assert.DoesNotContain(events.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);

    private async Task<WorkflowEvent[]> RunWorkflowAsync(
        string workflowFile,
        List<AgentResponseUpdate>? updates,
        bool throwOnInvoke = false)
    {
        List<WorkflowEvent> events = [];

        Workflow workflow = CreateWorkflow(workflowFile, updates, throwOnInvoke);
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "Test input message");

        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            events.Add(workflowEvent);
            this.Output.WriteLine($"EVENT: {workflowEvent.GetType().Name} {Describe(workflowEvent)}");
        }

        return [.. events];
    }

    private static string Describe(WorkflowEvent workflowEvent) =>
        workflowEvent switch
        {
            ExecutorCompletedEvent e => e.ExecutorId,
            ExecutorFailedEvent e => $"{e.ExecutorId}: {e.Data?.Message}",
            AgentResponseEvent e => $"messages={e.Response.Messages.Count}",
            _ => string.Empty,
        };

    private static Workflow CreateWorkflow(string workflowFile, List<AgentResponseUpdate>? updates, bool throwOnInvoke)
    {
        Mock<ResponseAgentProvider> provider = new(MockBehavior.Strict);
        provider.Setup(p => p.CreateConversationAsync(It.IsAny<CancellationToken>()))
                .Returns(() => Task.FromResult(Guid.NewGuid().ToString("N")));
        provider.Setup(p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
                .Returns<string, ChatMessage, CancellationToken>((_, message, _) => Task.FromResult(message));
        provider.Setup(
            p => p.InvokeAgentAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string?>(),
                It.IsAny<IEnumerable<ChatMessage>?>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() => throwOnInvoke ? ThrowAsync() : AgentUpdateTestHelpers.ToAsyncEnumerableAsync(updates ?? []));

        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowFile));
        DeclarativeWorkflowOptions options = new(provider.Object);
        return DeclarativeWorkflowBuilder.Build<string>(yamlReader, options);
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ThrowAsync()
    {
        await Task.CompletedTask;
        throw new InvalidOperationException("Simulated transport failure");
#pragma warning disable CS0162 // Unreachable code detected
        yield break;
#pragma warning restore CS0162
    }
}
