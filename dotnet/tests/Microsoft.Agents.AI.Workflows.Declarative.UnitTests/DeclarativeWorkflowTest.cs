// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx.Types;
using Moq;
using Shared.UnitTests;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeWorkflowTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private List<WorkflowEvent> WorkflowEvents { get; } = [];

    private Dictionary<Type, int> WorkflowEventCounts { get; set; } = [];

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ResumeAsync_LegacyCheckpointPreservesNextAssignmentAsync(bool offThread, bool clear)
    {
        // Arrange
        (Workflow workflow, CheckpointManager checkpoints, CheckpointInfo checkpoint) =
            await CreateLegacyCheckpointAsync(offThread, clear, completed: false);
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);

        // Act
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, checkpoint);
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
        {
            Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
        }

        // Assert
        WorkflowFormulaState state = GetRootState(workflow);
        Assert.Equal(clear ? null : "updated", state.Get("TestValue").ToObject());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ResumeAsync_LegacyCheckpointSupportsImmediateRestoresAsync(bool offThread)
    {
        // Arrange
        (Workflow workflow, CheckpointManager checkpoints, CheckpointInfo checkpoint) =
            await CreateLegacyCheckpointAsync(offThread, clear: false, completed: true);
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);

        // Act
        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, checkpoint);
        await resumed.RestoreCheckpointAsync(checkpoint);
        await resumed.RestoreCheckpointAsync(checkpoint);

        // Assert
        Assert.Equal("updated", GetRootState(workflow).Get("TestValue").ToObject());
    }

    private static async Task<(Workflow Workflow, CheckpointManager Checkpoints, CheckpointInfo Checkpoint)> CreateLegacyCheckpointAsync(
        bool offThread, bool clear, bool completed)
    {
        Dictionary<CheckpointInfo, JsonElement> stored = [];
        Mock<ICheckpointStore<JsonElement>> store = new();
        store.Setup(s => s.CreateCheckpointAsync(It.IsAny<string>(), It.IsAny<JsonElement>(), It.IsAny<CheckpointInfo?>()))
            .ReturnsAsync((string sessionId, JsonElement value, CheckpointInfo? _) =>
            {
                CheckpointInfo info = new(sessionId, Guid.NewGuid().ToString("N"));
                stored.Add(info, value);
                return info;
            });
        store.Setup(s => s.RetrieveCheckpointAsync(It.IsAny<string>(), It.IsAny<CheckpointInfo>()))
            .ReturnsAsync((string _, CheckpointInfo info) => stored[info]);
        store.Setup(s => s.RetrieveIndexAsync(It.IsAny<string>(), It.IsAny<CheckpointInfo?>()))
            .ReturnsAsync((string sessionId, CheckpointInfo? _) =>
                stored.Keys.Where(info => string.Equals(info.SessionId, sessionId, StringComparison.Ordinal)).ToArray().AsEnumerable());
        CheckpointManager checkpoints = CheckpointManager.CreateJson(store.Object, DeclarativeWorkflowJsonOptions.Default);
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        List<CheckpointInfo> saved = [];
        await using (StreamingRun run = await environment.RunStreamingAsync(BuildWorkflow(), "start"))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                Assert.False(evt is WorkflowErrorEvent, (evt as WorkflowErrorEvent)?.Exception?.ToString());
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    saved.Add(checkpoint);
                }
            }
        }
        Assert.True(saved.Count >= 3);
        CheckpointInfo legacy = completed ? saved[^1] : saved.First(info =>
            stored[info].GetProperty("stateData").EnumerateObject().Any(entry =>
                entry.Name.EndsWith("|@Local|TestValue", StringComparison.Ordinal)));
        JsonNode? node = JsonNode.Parse(stored[legacy].GetRawText());
        Assert.NotNull(node);
        JsonObject stateData = Assert.IsType<JsonObject>(node["stateData"]);
        string localKey = Assert.Single(stateData.Select(entry => entry.Key),
            key => key.EndsWith("|@Local|TestValue", StringComparison.Ordinal));
        JsonNode? value = stateData[localKey];
        Assert.True(stateData.Remove(localKey));
        stateData.Add(localKey.Replace("|@Local|", "|@Topic|"), value);
        Assert.True(stateData.Remove(localKey.Replace("|@Local|", $"|@{WorkflowFormulaState.LocalOwnershipScopeName}|")));
        stored[legacy] = JsonSerializer.SerializeToElement(node);
        return (BuildWorkflow(), checkpoints, legacy);

        Workflow BuildWorkflow()
        {
            using StringReader reader = new($$"""
                kind: Workflow
                trigger:
                  kind: OnConversationStart
                  id: legacy_restore
                  actions:
                    - kind: SetVariable
                      id: seed_value
                      variable: Local.TestValue
                      value: legacy
                    - kind: SetVariable
                      id: update_value
                      variable: Topic.TestValue
                      value: {{(clear ? "=Blank()" : "updated")}}
                """);
            return DeclarativeWorkflowBuilder.Build<string>(reader, new(new MockAgentProvider().Object));
        }
    }

    [Theory]
    [InlineData("BadEmpty.yaml")]
    [InlineData("BadId.yaml")]
    [InlineData("BadKind.yaml")]
    public async Task InvalidWorkflowAsync(string workflowFile)
    {
        await Assert.ThrowsAsync<DeclarativeModelException>(() => this.RunWorkflowAsync(workflowFile));
        this.AssertNotExecuted("end_all");
    }

    [Fact]
    public async Task LoopEachActionAsync()
    {
        await this.RunWorkflowAsync("LoopEach.yaml");
        this.AssertExecutionCount(expectedCount: 34);
        this.AssertExecuted("foreach_loop");
        this.AssertExecuted("set_variable_inner");
        this.AssertExecuted("send_activity_inner");
        this.AssertExecuted("end_all");
    }

    [Fact]
    public async Task LoopBreakActionAsync()
    {
        await this.RunWorkflowAsync("LoopBreak.yaml");
        this.AssertExecutionCount(expectedCount: 6);
        this.AssertExecuted("foreach_loop", isDiscrete: false);
        this.AssertExecuted("break_loop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("set_variable_inner");
        this.AssertNotExecuted("send_activity_inner");
    }

    [Fact]
    public async Task LoopContinueActionAsync()
    {
        await this.RunWorkflowAsync("LoopContinue.yaml");
        this.AssertExecutionCount(expectedCount: 22);
        this.AssertExecuted("foreach_loop", isDiscrete: false);
        this.AssertExecuted("continue_loop_now");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("set_variable_inner");
        this.AssertNotExecuted("send_activity_inner");
    }

    [Fact]
    public async Task EndConversationActionAsync()
    {
        await this.RunWorkflowAsync("EndConversation.yaml");
        this.AssertExecutionCount(expectedCount: 1);
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("sendActivity_1");
    }

    [Fact]
    public async Task HostedWorkflowAgentIsolatesDeclarativeStateBySessionAsync()
    {
        // Arrange
        RecordingAgentProvider provider = new();
        AIAgent agent = CreateStateEchoWorkflow(provider).AsAIAgent(id: "host", name: "host");
        AgentSession aliceSession = await agent.CreateSessionAsync();
        AgentSession mallorySession = await agent.CreateSessionAsync();

        // Act
        AgentResponse aliceSeedResponse = await agent.RunAsync("EMBER-QUARTZ-7319", aliceSession);
        AgentResponse aliceResumeResponse = await agent.RunAsync("inspect-alice", aliceSession);
        AgentResponse malloryInspectResponse = await agent.RunAsync("inspect-mallory", mallorySession);
        _ = await agent.RunAsync("ONYX-CEDAR-4826", mallorySession);
        AgentResponse aliceFinalResponse = await agent.RunAsync("inspect-alice-again", aliceSession);

        // Assert
        Assert.NotSame(aliceSession, mallorySession);
        Assert.Contains("Marker: \"\"", aliceSeedResponse.Text, StringComparison.Ordinal);
        Assert.Contains("EMBER-QUARTZ-7319", aliceResumeResponse.Text, StringComparison.Ordinal);
        Assert.DoesNotContain("EMBER-QUARTZ-7319", malloryInspectResponse.Text, StringComparison.Ordinal);
        Assert.DoesNotContain("ONYX-CEDAR-4826", aliceFinalResponse.Text, StringComparison.Ordinal);
        Assert.Contains("inspect-alice", aliceFinalResponse.Text, StringComparison.Ordinal);

        Assert.True(provider.MessageConversations.Count >= 3);
        Assert.Equal(provider.MessageConversations[0], provider.MessageConversations[1]);
        Assert.NotEqual(provider.MessageConversations[0], provider.MessageConversations[2]);
    }

    [Fact]
    public async Task HostedWorkflowAgentIsolatesDeclarativeStateForImplicitSessionsAsync()
    {
        // Arrange
        RecordingAgentProvider provider = new();
        AIAgent agent = CreateStateEchoWorkflow(provider).AsAIAgent(id: "host", name: "host");

        // Act
        _ = await agent.RunAsync("EMBER-QUARTZ-7319");
        AgentResponse secondImplicitResponse = await agent.RunAsync("inspect-implicit");

        // Assert
        Assert.DoesNotContain("EMBER-QUARTZ-7319", secondImplicitResponse.Text, StringComparison.Ordinal);
        Assert.True(provider.MessageConversations.Count >= 2);
        Assert.NotEqual(provider.MessageConversations[0], provider.MessageConversations[1]);
    }

    [Fact]
    public async Task Build_OnlyInitializesAllowedReferencedEnvironmentVariablesAsync()
    {
        // Arrange
        const string AllowedName = "AllowedConfig";
        const string HiddenName = "HiddenConfig";
        const string ProcessOnlyName = "ProcessOnlyConfig";
        const string ProcessOnlyValue = "process-value";

        string? originalProcessOnlyValue = Environment.GetEnvironmentVariable(ProcessOnlyName);
        Environment.SetEnvironmentVariable(ProcessOnlyName, ProcessOnlyValue);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [AllowedName] = "allowed-value",
                    [HiddenName] = "hidden-value",
                })
                .Build();
            using StringReader yamlReader = new(
                """
                    kind: Workflow
                    trigger:

                      kind: OnConversationStart
                      id: env_boundary_workflow
                      actions:

                        - kind: SetVariable
                          id: referenced_allowed_configuration
                          variable: Local.Allowed
                          value: =Env.AllowedConfig

                        - kind: SetVariable
                          id: referenced_hidden_configuration
                          disabled: true
                          variable: Local.Hidden
                          value: =Env.HiddenConfig

                        - kind: SetVariable
                          id: referenced_process_configuration
                          disabled: true
                          variable: Local.ProcessOnly
                          value: =Env.ProcessOnlyConfig
                    """);
            Mock<ResponseAgentProvider> mockAgentProvider = CreateMockProvider("Test input message");
            DeclarativeWorkflowOptions options =
                new(mockAgentProvider.Object)
                {
                    Configuration = configuration,
                    AllowedEnvironmentVariables = [AllowedName, ProcessOnlyName],
                    LoggerFactory = this.Output,
                };
            Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(yamlReader, options);
            WorkflowFormulaState rootState = GetRootState(workflow);

            // Act
            await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "Test input message");

            await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
            {
                this.WorkflowEvents.Add(workflowEvent);
                if (workflowEvent is WorkflowErrorEvent errorEvent)
                {
                    throw errorEvent.Data as Exception ?? new XunitException("Unexpected failure...");
                }
            }

            // Assert
            StringValue allowedValue = Assert.IsType<StringValue>(rootState.Get(AllowedName, VariableScopeNames.Environment));
            Assert.Equal("allowed-value", allowedValue.Value);
            Assert.IsType<BlankValue>(rootState.Get(HiddenName, VariableScopeNames.Environment));
            Assert.IsType<BlankValue>(rootState.Get(ProcessOnlyName, VariableScopeNames.Environment));
            Assert.Equal(SensitivityLevel.Sensitive, rootState.GetSensitivity(AllowedName, VariableScopeNames.Environment));
        }
        finally
        {
            Environment.SetEnvironmentVariable(ProcessOnlyName, originalProcessOnlyValue);
        }
    }

    [Fact]
    public async Task Build_WithProcessEnvironmentFallback_LoadsAllowedMissingConfigurationFromProcessEnvironmentAsync()
    {
        // Arrange
        const string ProcessOnlyName = "ProcessOnlyConfigForFallback";
        const string ExplicitName = "ExplicitConfigWinsForFallback";
        const string HiddenName = "HiddenConfigForFallback";
        const string ProcessOnlyValue = "process-only-value";
        const string ExplicitConfigurationValue = "configuration-value";
        const string ExplicitProcessValue = "process-value";
        const string HiddenValue = "hidden-value";

        string? originalProcessOnlyValue = Environment.GetEnvironmentVariable(ProcessOnlyName);
        string? originalExplicitValue = Environment.GetEnvironmentVariable(ExplicitName);
        string? originalHiddenValue = Environment.GetEnvironmentVariable(HiddenName);
        Environment.SetEnvironmentVariable(ProcessOnlyName, ProcessOnlyValue);
        Environment.SetEnvironmentVariable(ExplicitName, ExplicitProcessValue);
        Environment.SetEnvironmentVariable(HiddenName, HiddenValue);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    [ExplicitName] = ExplicitConfigurationValue,
                })
                .Build();
            using StringReader yamlReader = new(
                """
                    kind: Workflow
                    trigger:

                      kind: OnConversationStart
                      id: env_fallback_workflow
                      actions:

                        - kind: SetVariable
                          id: referenced_process_configuration
                          variable: Local.ProcessOnly
                          value: =Env.ProcessOnlyConfigForFallback

                        - kind: SetVariable
                          id: referenced_explicit_configuration
                          variable: Local.Explicit
                          value: =Env.ExplicitConfigWinsForFallback

                        - kind: SetVariable
                          id: referenced_hidden_process_environment
                          disabled: true
                          variable: Local.Hidden
                          value: =Env.HiddenConfigForFallback
                    """);
            Mock<ResponseAgentProvider> mockAgentProvider = CreateMockProvider("Test input message");
            DeclarativeWorkflowOptions options =
                new(mockAgentProvider.Object)
                {
                    Configuration = configuration,
                    AllowedEnvironmentVariables = [ProcessOnlyName, ExplicitName],
                    AllowProcessEnvironmentVariableFallback = true,
                    LoggerFactory = this.Output,
                };
            Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(yamlReader, options);
            WorkflowFormulaState rootState = GetRootState(workflow);

            // Act
            await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "Test input message");

            await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
            {
                this.WorkflowEvents.Add(workflowEvent);
                if (workflowEvent is WorkflowErrorEvent errorEvent)
                {
                    throw errorEvent.Data as Exception ?? new XunitException("Unexpected failure...");
                }
            }

            // Assert
            StringValue processOnlyValue = Assert.IsType<StringValue>(rootState.Get(ProcessOnlyName, VariableScopeNames.Environment));
            Assert.Equal(ProcessOnlyValue, processOnlyValue.Value);
            StringValue explicitValue = Assert.IsType<StringValue>(rootState.Get(ExplicitName, VariableScopeNames.Environment));
            Assert.Equal(ExplicitConfigurationValue, explicitValue.Value);
            Assert.IsType<BlankValue>(rootState.Get(HiddenName, VariableScopeNames.Environment));
            Assert.Equal(SensitivityLevel.Sensitive, rootState.GetSensitivity(ProcessOnlyName, VariableScopeNames.Environment));
            Assert.Equal(SensitivityLevel.Sensitive, rootState.GetSensitivity(ExplicitName, VariableScopeNames.Environment));
        }
        finally
        {
            Environment.SetEnvironmentVariable(ProcessOnlyName, originalProcessOnlyValue);
            Environment.SetEnvironmentVariable(ExplicitName, originalExplicitValue);
            Environment.SetEnvironmentVariable(HiddenName, originalHiddenValue);
        }
    }

    [Theory]
    [InlineData("enabled")]
    [InlineData("disabled")]
    public async Task ConditionRejectsEnvironmentInputBeforeBranchActionsAsync(string setting)
    {
        // Arrange
        using StringReader reader = new(
            """
            kind: Workflow
            trigger:
              kind: OnConversationStart
              id: condition_validation
              actions:
                - kind: ConditionGroup
                  id: select_branch
                  conditions:
                    - id: enabled_branch
                      condition: =Left(Env.Setting, 2) = "en"
                      actions:
                        - kind: SendActivity
                          id: enabled_activity
                          activity: Enabled
                  elseActions:
                    - kind: SendActivity
                      id: disabled_activity
                      activity: Disabled
            """);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["Setting"] = setting })
            .Build();
        DeclarativeWorkflowOptions options = new(CreateMockProvider("input").Object)
        {
            Configuration = configuration,
            AllowedEnvironmentVariables = ["Setting"],
        };
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(reader, options);

        // Act
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "input");
        WorkflowEvent[] events = await run.WatchStreamAsync().ToArrayAsync();

        // Assert
        ExecutorFailedEvent failure = Assert.Single(events.OfType<ExecutorFailedEvent>());
        DeclarativeActionException exception = Assert.IsType<DeclarativeActionException>(failure.Data);
        Assert.Contains("condition", exception.Message);
        Assert.Empty(events.OfType<MessageActivityEvent>());
        Assert.DoesNotContain(events.OfType<DeclarativeActionInvokedEvent>(),
            e => string.Equals(e.ActionId, "enabled_activity", StringComparison.Ordinal) ||
                 string.Equals(e.ActionId, "disabled_activity", StringComparison.Ordinal));
    }

    [Fact]
    public async Task GotoActionAsync()
    {
        await this.RunWorkflowAsync("Goto.yaml");
        this.AssertExecutionCount(expectedCount: 2);
        this.AssertExecuted("goto_end");
        this.AssertExecuted("end_all");
        this.AssertNotExecuted("sendActivity_1");
        this.AssertNotExecuted("sendActivity_2");
        this.AssertNotExecuted("sendActivity_3");
    }

    [Theory]
    [InlineData(12)]
    [InlineData(37)]
    public async Task ConditionActionAsync(int input)
    {
        await this.RunWorkflowAsync("Condition.yaml", input);
        this.AssertExecutionCount(expectedCount: 9);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test");
        if (input % 2 == 0)
        {
            this.AssertExecuted("conditionItem_even", isAction: false);
            this.AssertExecuted("sendActivity_even");
            this.AssertNotExecuted("conditionItem_odd");
            this.AssertNotExecuted("sendActivity_odd");
            this.AssertMessage("EVEN");
        }
        else
        {
            this.AssertExecuted("conditionItem_odd", isAction: false);
            this.AssertExecuted("sendActivity_odd");
            this.AssertNotExecuted("conditionItem_even");
            this.AssertNotExecuted("sendActivity_even");
            this.AssertMessage("ODD");
        }
        this.AssertExecuted("activity_final");
    }

    [Theory]
    [InlineData(12, 7)]
    [InlineData(37, 9)]
    public async Task ConditionActionWithElseAsync(int input, int expectedActions)
    {
        await this.RunWorkflowAsync("ConditionElse.yaml", input);
        this.AssertExecutionCount(expectedActions);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test");
        if (input % 2 == 0)
        {
            this.AssertExecuted("sendActivity_else", isAction: false);
            this.AssertNotExecuted("conditionItem_odd");
            this.AssertNotExecuted("sendActivity_odd");
        }
        else
        {
            this.AssertExecuted("conditionItem_odd", isAction: false);
            this.AssertExecuted("sendActivity_odd");
            this.AssertNotExecuted("sendActivity_else");
        }
        this.AssertExecuted("activity_final");
    }

    [Theory]
    [InlineData(12, 4)]
    [InlineData(37, 9)]
    public async Task ConditionActionWithFallThroughAsync(int input, int expectedActions)
    {
        await this.RunWorkflowAsync("ConditionFallThrough.yaml", input);
        this.AssertExecutionCount(expectedActions);
        this.AssertExecuted("setVariable_test");
        this.AssertExecuted("conditionGroup_test", isAction: false);
        if (input % 2 == 0)
        {
            this.AssertNotExecuted("conditionItem_odd");
            this.AssertNotExecuted("sendActivity_odd");
        }
        else
        {
            this.AssertExecuted("conditionItem_odd", isAction: false);
            this.AssertExecuted("sendActivity_odd");
            this.AssertMessage("ODD");
        }
        this.AssertExecuted("activity_final");
    }

    [Theory]
    [InlineData("CancelWorkflow.yaml", 1, "end_all")]
    [InlineData("EndConversation.yaml", 1, "end_all")]
    [InlineData("EndWorkflow.yaml", 1, "end_all")]
    [InlineData("EditTable.yaml", 2, "edit_var")]
    [InlineData("EditTableV2.yaml", 2, "edit_var")]
    [InlineData("ParseValue.yaml", 2, "parse_var")]
    [InlineData("ParseValueList.yaml", 2, "parse_var")]
    [InlineData("SendActivity.yaml", 2, "activity_input")]
    [InlineData("SetVariable.yaml", 1, "set_var")]
    [InlineData("SetTextVariable.yaml", 1, "set_text")]
    [InlineData("ClearAllVariables.yaml", 1, "clear_all")]
    [InlineData("ResetVariable.yaml", 2, "clear_var")]
    [InlineData("MixedScopes.yaml", 2, "activity_input")]
    [InlineData("CaseInsensitive.yaml", 6, "end_when_match")]
    [InlineData("HttpRequest.yaml", 1, "http_request")]
    public async Task ExecuteActionAsync(string workflowFile, int expectedCount, string expectedId)
    {
        await this.RunWorkflowAsync(workflowFile);
        this.AssertExecutionCount(expectedCount);
        this.AssertExecuted(expectedId);
    }

    [Theory]
    [InlineData(typeof(ActivateExternalTrigger.Builder))]
    [InlineData(typeof(AdaptiveCardPrompt.Builder))]
    [InlineData(typeof(BeginDialog.Builder))]
    [InlineData(typeof(CSATQuestion.Builder))]
    [InlineData(typeof(CreateSearchQuery.Builder))]
    [InlineData(typeof(DeleteActivity.Builder))]
    [InlineData(typeof(DisableTrigger.Builder))]
    [InlineData(typeof(DisconnectedNodeContainer.Builder))]
    [InlineData(typeof(EmitEvent.Builder))]
    [InlineData(typeof(GetActivityMembers.Builder))]
    [InlineData(typeof(GetConversationMembers.Builder))]
    [InlineData(typeof(InvokeAIBuilderModelAction.Builder))]
    [InlineData(typeof(InvokeConnectorAction.Builder))]
    [InlineData(typeof(InvokeMcpToolAction.Builder))]
    [InlineData(typeof(VoiceAuthenticate.Builder))]
    [InlineData(typeof(InvokeCustomModelAction.Builder))]
    [InlineData(typeof(InvokeFlowAction.Builder))]
    [InlineData(typeof(InvokeSkillAction.Builder))]
    [InlineData(typeof(LogCustomTelemetryEvent.Builder))]
    [InlineData(typeof(OAuthInput.Builder))]
    [InlineData(typeof(RecognizeIntent.Builder))]
    [InlineData(typeof(RepeatDialog.Builder))]
    [InlineData(typeof(ReplaceDialog.Builder))]
    [InlineData(typeof(SearchAndSummarizeContent.Builder))]
    [InlineData(typeof(SearchAndSummarizeWithCustomModel.Builder))]
    [InlineData(typeof(SearchKnowledgeSources.Builder))]
    [InlineData(typeof(SignOutUser.Builder))]
    [InlineData(typeof(TransferConversation.Builder))]
    [InlineData(typeof(TransferConversationV2.Builder))]
    [InlineData(typeof(UnknownDialogAction.Builder))]
    [InlineData(typeof(UpdateActivity.Builder))]
    [InlineData(typeof(WaitForConnectorTrigger.Builder))]
    public void UnsupportedAction(Type type)
    {
        DialogAction.Builder? unsupportedAction = (DialogAction.Builder?)Activator.CreateInstance(type);
        Assert.NotNull(unsupportedAction);
        unsupportedAction.Id = "action_bad";
        AdaptiveDialog.Builder dialogBuilder =
            new()
            {
                BeginDialog =
                    new OnActivity.Builder()
                    {
                        Id = "anything",
                        Actions = [unsupportedAction]
                    }
            };
        AdaptiveDialog dialog = dialogBuilder.Build();

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        Mock<ResponseAgentProvider> mockAgentProvider = CreateMockProvider("1");
        DeclarativeWorkflowOptions options = new(mockAgentProvider.Object);
        WorkflowActionVisitor visitor = new(new DeclarativeWorkflowExecutor<string>(WorkflowActionVisitor.Steps.Root("anything"), options, state, (message) => DeclarativeWorkflowBuilder.DefaultTransform(message)), state, options);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(dialog);
        Assert.True(visitor.HasUnsupportedActions);
    }

    [Fact]
    public void UnsupportedActionLogsWarning()
    {
        SearchKnowledgeSources.Builder unsupportedAction = new() { Id = "action_bad" };
        AdaptiveDialog.Builder dialogBuilder =
            new()
            {
                BeginDialog =
                    new OnActivity.Builder()
                    {
                        Id = "anything",
                        Actions = [unsupportedAction]
                    }
            };
        AdaptiveDialog dialog = dialogBuilder.Build();

        WorkflowFormulaState state = new(RecalcEngineFactory.Create());
        Mock<ResponseAgentProvider> mockAgentProvider = CreateMockProvider("1");
        CapturingLoggerFactory loggerFactory = new();
        DeclarativeWorkflowOptions options = new(mockAgentProvider.Object) { LoggerFactory = loggerFactory };
        WorkflowActionVisitor visitor = new(new DeclarativeWorkflowExecutor<string>(WorkflowActionVisitor.Steps.Root("anything"), options, state, (message) => DeclarativeWorkflowBuilder.DefaultTransform(message)), state, options);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(dialog);

        Assert.True(visitor.HasUnsupportedActions);
        (LogLevel Level, string Message) warning = Assert.Single(loggerFactory.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Contains(nameof(SearchKnowledgeSources), warning.Message, StringComparison.Ordinal);
        Assert.Contains("action_bad", warning.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("CaseInsensitive.yaml", "end_when_match")]
    [InlineData("ClearAllVariables.yaml", "clear_all")]
    [InlineData("Condition.yaml", "setVariable_test")]
    [InlineData("ConditionElse.yaml", "setVariable_test")]
    [InlineData("EndConversation.yaml", "end_all")]
    [InlineData("EndWorkflow.yaml", "end_all")]
    [InlineData("EditTable.yaml", "edit_var")]
    [InlineData("EditTableV2.yaml", "edit_var")]
    [InlineData("Goto.yaml", "goto_end")]
    [InlineData("LoopBreak.yaml", "break_loop_now")]
    [InlineData("LoopContinue.yaml", "foreach_loop")]
    [InlineData("LoopEach.yaml", "foreach_loop")]
    [InlineData("MixedScopes.yaml", "activity_input")]
    [InlineData("ParseValue.yaml", "parse_var")]
    [InlineData("ParseValueList.yaml", "parse_var")]
    [InlineData("ResetVariable.yaml", "clear_var")]
    [InlineData("SendActivity.yaml", "activity_input")]
    [InlineData("SetVariable.yaml", "set_var")]
    [InlineData("SetTextVariable.yaml", "set_text")]
    [InlineData("HttpRequest.yaml", "http_request")]
    public async Task CancelRunAsync(string workflowPath, string expectedExecutedId)
    {
        // Arrange
        const string WorkflowInput = "Test input message";
        Workflow workflow = this.CreateWorkflow(workflowPath, WorkflowInput);
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow: workflow, input: WorkflowInput);

        // Act
        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            this.WorkflowEvents.Add(workflowEvent);

            if (workflowEvent is DeclarativeActionInvokedEvent actionInvokedEvent && actionInvokedEvent.ActionId == expectedExecutedId)
            {
                // Cancel run after the specified declarative action is invoked.
                await run.CancelRunAsync();
            }
        }
        RunStatus currentRunStatus = await run.GetStatusAsync();
        this.WorkflowEventCounts = this.WorkflowEvents.GroupBy(e => e.GetType()).ToDictionary(e => e.Key, e => e.Count());

        // Assert
        Assert.Equal(expected: RunStatus.Ended, actual: currentRunStatus);
        Assert.NotEmpty(this.WorkflowEventCounts);
        Assert.Contains(this.WorkflowEvents.OfType<DeclarativeActionInvokedEvent>(), e => e.ActionId == expectedExecutedId);
        Assert.DoesNotContain(this.WorkflowEvents.OfType<DeclarativeActionCompletedEvent>(), e => e.ActionId == expectedExecutedId);
    }

    private void AssertExecutionCount(int expectedCount)
    {
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorInvokedEvent)]);
        Assert.Equal(expectedCount + 2, this.WorkflowEventCounts[typeof(ExecutorCompletedEvent)]);
    }

    private void AssertNotExecuted(string executorId)
    {
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorInvokedEvent>(), e => e.ExecutorId == executorId);
        Assert.DoesNotContain(this.WorkflowEvents.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);
    }

    private void AssertExecuted(string executorId, bool isAction = true, bool isDiscrete = true)
    {
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorInvokedEvent>(), e => e.ExecutorId == executorId);
        Assert.Contains(this.WorkflowEvents.OfType<ExecutorCompletedEvent>(), e => e.ExecutorId == executorId);
        if (isAction)
        {
            Assert.Contains(this.WorkflowEvents.OfType<DeclarativeActionInvokedEvent>(), e => e.ActionId == executorId);
            if (isDiscrete)
            {
                Assert.Contains(this.WorkflowEvents.OfType<DeclarativeActionCompletedEvent>(), e => e.ActionId == executorId);
            }
        }
    }

    private void AssertMessage(string message) =>
        Assert.Contains(this.WorkflowEvents.OfType<MessageActivityEvent>(), e => string.Equals(e.Message.Trim(), message, StringComparison.Ordinal));

    private static WorkflowFormulaState GetRootState(Workflow workflow)
    {
        ExecutorBinding rootBinding = workflow.ReflectExecutors()[workflow.StartExecutorId];
        Executor rootExecutor = Assert.IsAssignableFrom<Executor>(rootBinding.RawValue);
        FieldInfo stateField = Assert.Single(rootExecutor.GetType().GetFields(BindingFlags.Instance | BindingFlags.NonPublic), field => field.FieldType == typeof(WorkflowFormulaState));
        return Assert.IsType<WorkflowFormulaState>(stateField.GetValue(rootExecutor));
    }

    private Task RunWorkflowAsync(string workflowPath) =>
        this.RunWorkflowAsync(workflowPath, "Test input message");

    private async Task RunWorkflowAsync<TInput>(string workflowPath, TInput workflowInput) where TInput : notnull
    {
        Workflow workflow = this.CreateWorkflow(workflowPath, workflowInput);
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, workflowInput);

        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync())
        {
            this.WorkflowEvents.Add(workflowEvent);

            switch (workflowEvent)
            {
                case ExecutorInvokedEvent invokeEvent:
                    ActionExecutorResult? message = invokeEvent.Data as ActionExecutorResult;
                    this.Output.WriteLine($"EXEC: {invokeEvent.ExecutorId} << {message?.ExecutorId ?? "?"} [{message?.Result ?? "-"}]");
                    break;

                case DeclarativeActionInvokedEvent actionInvokeEvent:
                    this.Output.WriteLine($"ACTION ENTER: {actionInvokeEvent.ActionId}");
                    break;

                case DeclarativeActionCompletedEvent actionCompleteEvent:
                    this.Output.WriteLine($"ACTION EXIT: {actionCompleteEvent.ActionId}");
                    break;

                case MessageActivityEvent activityEvent:
                    this.Output.WriteLine($"ACTIVITY: {activityEvent.Message}");
                    break;

                case AgentResponseEvent messageEvent:
                    this.Output.WriteLine($"MESSAGE: {messageEvent.Response.Messages[0].Text.Trim()}");
                    break;

                case ExecutorFailedEvent failureEvent:
                    Console.WriteLine($"Executor failed [{failureEvent.ExecutorId}]: {failureEvent.Data?.Message ?? "Unknown"}");
                    break;

                case WorkflowErrorEvent errorEvent:
                    throw errorEvent.Data as Exception ?? new XunitException("Unexpected failure...");
            }
        }

        this.WorkflowEventCounts = this.WorkflowEvents.GroupBy(e => e.GetType()).ToDictionary(e => e.Key, e => e.Count());
    }

    private Workflow CreateWorkflow<TInput>(string workflowPath, TInput workflowInput) where TInput : notnull
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowPath));
        Mock<ResponseAgentProvider> mockAgentProvider = CreateMockProvider($"{workflowInput}");
        DeclarativeWorkflowOptions workflowContext =
            new(mockAgentProvider.Object)
            {
                LoggerFactory = this.Output,
                HttpRequestHandler = CreateMockHttpRequestHandler().Object,
            };
        return DeclarativeWorkflowBuilder.Build<TInput>(yamlReader, workflowContext);
    }

    private static Workflow CreateStateEchoWorkflow(ResponseAgentProvider provider)
    {
        using StringReader yamlReader = new(
            """
                kind: Workflow
                trigger:

                  kind: OnConversationStart
                  id: state_echo_workflow
                  actions:

                    - kind: SendActivity
                      id: show_marker
                      activity: |-
                        Marker: "{Local.Marker}"

                    - kind: SetVariable
                      id: set_marker
                      variable: Local.Marker
                      value: =System.LastMessageText
                """);
        DeclarativeWorkflowOptions options = new(provider);

        return DeclarativeWorkflowBuilder.Build<string>(yamlReader, options);
    }

    private sealed class RecordingAgentProvider : ResponseAgentProvider
    {
        public List<string> MessageConversations { get; } = [];

        private int _conversationCount;

        public override Task<string> CreateConversationAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult($"conversation-{Interlocked.Increment(ref this._conversationCount):D2}");

        public override Task<ChatMessage> CreateMessageAsync(
            string conversationId,
            ChatMessage conversationMessage,
            CancellationToken cancellationToken = default)
        {
            this.MessageConversations.Add(conversationId);
            return Task.FromResult(conversationMessage);
        }

        public override Task<ChatMessage> GetMessageAsync(
            string conversationId,
            string messageId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new ChatMessage(ChatRole.Assistant, string.Empty) { MessageId = messageId });

        public override async IAsyncEnumerable<AgentResponseUpdate> InvokeAgentAsync(
            string agentId,
            string? agentVersion,
            string? conversationId,
            IEnumerable<ChatMessage>? messages,
            IDictionary<string, object?>? inputArguments,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield break;
        }

        public override async IAsyncEnumerable<ChatMessage> GetMessagesAsync(
            string conversationId,
            int? limit = null,
            string? after = null,
            string? before = null,
            bool newestFirst = false,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield break;
        }
    }

    private static Mock<ResponseAgentProvider> CreateMockProvider(string input)
    {
        Mock<ResponseAgentProvider> mockAgentProvider = new(MockBehavior.Strict);
        mockAgentProvider.Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>())).Returns(() => Task.FromResult(Guid.NewGuid().ToString("N")));
        mockAgentProvider.Setup(provider => provider.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>())).Returns(Task.FromResult(new ChatMessage(ChatRole.Assistant, input)));
        return mockAgentProvider;
    }

    private static Mock<IHttpRequestHandler> CreateMockHttpRequestHandler()
    {
        Mock<IHttpRequestHandler> mockHandler = new(MockBehavior.Loose);
        mockHandler
            .Setup(handler => handler.SendAsync(It.IsAny<HttpRequestInfo>(), It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(new HttpRequestResult
            {
                StatusCode = 200,
                IsSuccessStatusCode = true,
                Body = "{\"ok\":true}",
            }));
        return mockHandler;
    }
}
