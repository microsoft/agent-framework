// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Server;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Tests workflow lifecycle mapping to AG-UI events.
/// </summary>
public sealed class AGUIWorkflowEventExtensionsTests
{
    [Fact]
    public async Task WithAGUIWorkflowEvents_MapsBalancedStepsAndPreservesOutputOnceAsync()
    {
        // Arrange
        AgentResponseUpdate textOne = CreateUpdate(raw: null, new TextContent("one"));
        AgentResponseUpdate textTwo = CreateUpdate(raw: null, new TextContent("two"));
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new WorkflowStartedEvent("workflow")),
            CreateUpdate(new SuperStepStartedEvent(1)),
            CreateUpdate(new ExecutorInvokedEvent("agent-1", "input")),
            textOne,
            CreateUpdate(new ExecutorCompletedEvent("agent-1", "result")),
            CreateUpdate(new SuperStepCompletedEvent(1)),
            CreateUpdate(new SuperStepStartedEvent(2)),
            CreateUpdate(new ExecutorInvokedEvent("agent-2", "input")),
            textTwo,
            CreateUpdate(new ExecutorCompletedEvent("agent-2", "result")),
            CreateUpdate(new SuperStepCompletedEvent(2)));

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.Select(static update => update.RawRepresentation).OfType<StepStartedEvent>()
            .Select(static evt => evt.StepName)
            .Should().Equal("superstep:1", "superstep:2");
        updates.Select(static update => update.RawRepresentation).OfType<StepFinishedEvent>()
            .Select(static evt => evt.StepName)
            .Should().Equal("superstep:1", "superstep:2");
        updates.Where(static update => update.Text.Length > 0).Should().Equal(textOne, textTwo);
        updates.Count(static update => update.Text == "one").Should().Be(1);
        updates.Count(static update => update.Text == "two").Should().Be(1);
        updates.Select(static update => update.RawRepresentation).OfType<RunStartedEvent>().Should().BeEmpty();
        updates.Select(static update => update.RawRepresentation).OfType<RunFinishedEvent>().Should().BeEmpty();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_UsesCustomEventsForConcurrentRepeatedExecutorsAsync()
    {
        // Arrange
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new ExecutorInvokedEvent("worker", "first")),
            CreateUpdate(new ExecutorInvokedEvent("worker", "second")),
            CreateUpdate(new ExecutorCompletedEvent("worker", "first-result")),
            CreateUpdate(new ExecutorCompletedEvent("worker", "second-result")));

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        CustomEvent[] events = [.. updates.Select(static update => update.RawRepresentation).OfType<CustomEvent>()];
        events.Select(static evt => evt.Name).Should().Equal(
            "maf.workflow.executor.invoked",
            "maf.workflow.executor.invoked",
            "maf.workflow.executor.completed",
            "maf.workflow.executor.completed");
        events.Should().AllSatisfy(static evt => evt.Value!.Value.GetProperty("executorId").GetString().Should().Be("worker"));
        updates.Select(static update => update.RawRepresentation).OfType<ActivitySnapshotEvent>().Should().BeEmpty();
        updates.Select(static update => update.RawRepresentation).OfType<ActivityDeltaEvent>().Should().BeEmpty();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_ClosesActiveStepBeforeExecutorFailureAsync()
    {
        // Arrange
        AgentResponseUpdate failure = CreateUpdate(
            new ExecutorFailedEvent("worker", new InvalidOperationException("secret")),
            new ErrorContent("An error occurred while executing the workflow."));
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new SuperStepStartedEvent(7)),
            failure,
            CreateUpdate(new SuperStepCompletedEvent(7)));

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.Should().HaveCount(5);
        updates[0].RawRepresentation.Should().BeOfType<StepStartedEvent>();
        updates[1].RawRepresentation.Should().BeOfType<StepFinishedEvent>();
        CustomEvent failedEvent = updates[2].RawRepresentation.Should().BeOfType<CustomEvent>().Subject;
        failedEvent.Name.Should().Be("maf.workflow.executor.failed");
        failedEvent.Value!.Value.GetRawText().Should().NotContain("secret");
        updates[3].Should().BeSameAs(failure);
        updates[3].Contents.Should().ContainSingle().Which.Should().BeOfType<ErrorContent>();
        updates[4].RawRepresentation.Should().BeOfType<SuperStepCompletedEvent>();
        updates.Select(static update => update.RawRepresentation).OfType<StepFinishedEvent>().Should().ContainSingle();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_ClosesActiveStepBeforeWorkflowErrorAsync()
    {
        // Arrange
        AgentResponseUpdate error = CreateUpdate(
            new WorkflowErrorEvent(new InvalidOperationException("secret")),
            new ErrorContent("An error occurred while executing the workflow."));
        AIAgent agent = new ScriptedAgent(CreateUpdate(new SuperStepStartedEvent(3)), error);

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.Select(static update => update.RawRepresentation).Should().HaveCount(3);
        updates[1].RawRepresentation.Should().BeOfType<StepFinishedEvent>();
        updates[2].Should().BeSameAs(error);
        updates[2].Contents.Should().ContainSingle().Which.Should().BeOfType<ErrorContent>();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_MapsWarningAndSerializableNonChatOutputAsync()
    {
        // Arrange
        using JsonDocument document = JsonDocument.Parse("""{"name":"value","count":42}""");
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new WorkflowWarningEvent("retrying")),
            CreateUpdate(new WorkflowOutputEvent(document.RootElement, "worker", OutputTag.Intermediate)));

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        CustomEvent warning = updates[0].RawRepresentation.Should().BeOfType<CustomEvent>().Subject;
        warning.Name.Should().Be("maf.workflow.warning");
        warning.Value!.Value.GetProperty("message").GetString().Should().Be("The workflow reported a warning.");

        CustomEvent output = updates[1].RawRepresentation.Should().BeOfType<CustomEvent>().Subject;
        output.Name.Should().Be("maf.workflow.output");
        JsonElement outputValue = output.Value!.Value;
        outputValue.GetProperty("executorId").GetString().Should().Be("worker");
        outputValue.GetProperty("tags").EnumerateArray().Select(static tag => tag.GetString()).Should().Equal("intermediate");
        outputValue.GetProperty("data").GetProperty("name").GetString().Should().Be("value");
        outputValue.GetProperty("data").GetProperty("count").GetInt32().Should().Be(42);
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_OmitsUnsafeNonChatOutputPayloadAsync()
    {
        // Arrange
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new WorkflowOutputEvent(new ThrowingOutputPayload(), "worker")));

        // Act
        AgentResponseUpdate update = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .SingleAsync();

        // Assert
        CustomEvent output = update.RawRepresentation.Should().BeOfType<CustomEvent>().Subject;
        output.Value!.Value.GetProperty("data").ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_OmitsNonFiniteOutputPayloadAsync()
    {
        // Arrange
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new WorkflowOutputEvent(double.NaN, "worker")));

        // Act
        AgentResponseUpdate update = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .SingleAsync();

        // Assert
        CustomEvent output = update.RawRepresentation.Should().BeOfType<CustomEvent>().Subject;
        output.Value!.Value.GetProperty("data").ValueKind.Should().Be(JsonValueKind.Null);
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_PreservesResponseCompatibleAndInterruptUpdatesAsync()
    {
        // Arrange
        AgentResponseUpdate workflowText = CreateUpdate(
            new WorkflowOutputEvent("text", "worker"),
            new TextContent("text"));
        RequestPort port = RequestPort.Create<string, string>("approval");
        AgentResponseUpdate interrupt = CreateUpdate(
            new RequestInfoEvent(ExternalRequest.Create(port, "approve", "request-1")),
            new FunctionCallContent("request-1", "approval", new Dictionary<string, object?>()));
        AgentResponseUpdate toolResult = CreateUpdate(
            raw: null,
            new FunctionResultContent("request-1", "approved"));
        AIAgent agent = new ScriptedAgent(workflowText, interrupt, toolResult);

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.Should().Equal(workflowText, interrupt, toolResult);
        updates.Count(static update => update.Text == "text").Should().Be(1);
        updates.SelectMany(static update => update.Contents).OfType<FunctionCallContent>().Should().ContainSingle();
        updates.SelectMany(static update => update.Contents).OfType<FunctionResultContent>().Should().ContainSingle();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_ClosesActiveStepWhenStreamCompletesAsync()
    {
        // Arrange
        AIAgent agent = new ScriptedAgent(CreateUpdate(new SuperStepStartedEvent(4)));

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.Select(static update => update.RawRepresentation).Should().HaveCount(2);
        updates[0].RawRepresentation.Should().BeOfType<StepStartedEvent>();
        updates[1].RawRepresentation.Should().BeOfType<StepFinishedEvent>();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_ForwardsOnlyOneTerminalErrorContentAsync()
    {
        // Arrange
        AgentResponseUpdate executorError = CreateUpdate(
            new ExecutorFailedEvent("worker", new InvalidOperationException("secret")),
            new ErrorContent("An error occurred while executing the workflow."));
        AgentResponseUpdate workflowError = CreateUpdate(
            new WorkflowErrorEvent(new InvalidOperationException("secret")),
            new ErrorContent("An error occurred while executing the workflow."));
        AIAgent agent = new ScriptedAgent(
            CreateUpdate(new SuperStepStartedEvent(5)),
            executorError,
            workflowError);

        // Act
        List<AgentResponseUpdate> updates = await agent
            .WithAGUIWorkflowEvents()
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        updates.SelectMany(static update => update.Contents).OfType<ErrorContent>().Should().ContainSingle();
        updates.Should().Contain(executorError);
        updates.Should().NotContain(workflowError);
        updates.Select(static update => update.RawRepresentation).OfType<StepFinishedEvent>().Should().ContainSingle();
    }

    [Fact]
    public async Task AsAGUIChatResponseUpdatesAsync_PreservesMappedBaseEventAsRawRepresentationAsync()
    {
        // Arrange
        StepStartedEvent stepStarted = new() { StepName = "superstep:1" };
        AgentResponseUpdate update = CreateUpdate(stepStarted);

        // Act
        ChatResponseUpdate chatUpdate = await ToAsyncEnumerableAsync(update)
            .AsAGUIChatResponseUpdatesAsync()
            .SingleAsync();

        // Assert
        chatUpdate.RawRepresentation.Should().BeSameAs(stepStarted);
    }

    [Fact]
    public async Task AGUIServer_DoesNotRecursivelyUnwrapNestedRawRepresentationAsync()
    {
        // Arrange
        StepStartedEvent stepStarted = new() { StepName = "superstep:1" };
        AgentResponseUpdate update = CreateUpdate(stepStarted);
        ChatResponseUpdate nestedUpdate = update.AsChatResponseUpdate();
        RunAgentInput input = new()
        {
            Messages = [],
            RunId = "run",
            ThreadId = "thread",
        };
        ChatRequestContext context = input.ToChatRequestContext(new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            TypeInfoResolver = new DefaultJsonTypeInfoResolver(),
        });

        // Act
        List<BaseEvent> events = await ToAsyncEnumerableAsync(nestedUpdate)
            .AsAGUIEventStreamAsync(context)
            .ToListAsync();

        // Assert
        events.OfType<StepStartedEvent>().Should().BeEmpty();
    }

    [Fact]
    public async Task WithAGUIWorkflowEvents_MapsRealSequentialWorkflowStepsAndTextAsync()
    {
        // Arrange
        Workflow workflow = new SequentialWorkflowBuilder(
            new ConstantAgent("first", "one"),
            new ConstantAgent("second", "two"))
            .Build();
        AIAgent agent = workflow
            .AsAIAgent()
            .WithAGUIWorkflowEvents();

        // Act
        List<AgentResponseUpdate> updates = await agent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"))
            .ToListAsync();

        // Assert
        string[] starts = [.. updates.Select(static update => update.RawRepresentation).OfType<StepStartedEvent>().Select(static evt => evt.StepName)];
        string[] finishes = [.. updates.Select(static update => update.RawRepresentation).OfType<StepFinishedEvent>().Select(static evt => evt.StepName)];
        starts.Should().NotBeEmpty();
        finishes.Should().Equal(starts);
        updates.Where(static update => update.Text is "one" or "two").Select(static update => update.Text)
            .Should().Equal("one", "two");
        updates.Count(static update => update.Text == "one").Should().Be(1);
        updates.Count(static update => update.Text == "two").Should().Be(1);
    }

    [Fact]
    public void WithAGUIWorkflowEvents_WithNullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgent agent = null!;

        // Act
        Action act = () => agent.WithAGUIWorkflowEvents();

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    private static AgentResponseUpdate CreateUpdate(object? raw, params AIContent[] contents)
        => new(ChatRole.Assistant, contents)
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
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

    private sealed class ThrowingOutputPayload
    {
        public string Value => throw new InvalidOperationException("secret");
    }

    private sealed class ScriptedAgent(params AgentResponseUpdate[] updates) : AIAgent
    {
        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => this.RunCoreStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (AgentResponseUpdate update in updates)
            {
                cancellationToken.ThrowIfCancellationRequested();
                yield return update;
            }
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new ScriptedAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(new ScriptedAgentSession());

        private sealed class ScriptedAgentSession : AgentSession;
    }

    private sealed class ConstantAgent(string name, string text) : AIAgent
    {
        public override string? Name => name;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, text)));

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new AgentResponseUpdate(ChatRole.Assistant, text)
            {
                AuthorName = name,
                MessageId = Guid.NewGuid().ToString("N"),
                ResponseId = Guid.NewGuid().ToString("N"),
            };
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new ConstantAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(new ConstantAgentSession());

        private sealed class ConstantAgentSession : AgentSession;
    }
}
