// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;
using ApprovalSnapshot = Microsoft.Agents.AI.Workflows.Declarative.ObjectModel.InvokeFunctionToolExecutor.ApprovalSnapshot;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="InvokeFunctionToolExecutor"/>.
/// </summary>
public sealed class InvokeFunctionToolExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    #region Step Naming Convention Tests

    [Fact]
    public void InvokeFunctionToolThrowsWhenModelInvalid() =>
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new InvokeFunctionToolExecutor(new InvokeFunctionTool(), new MockAgentProvider().Object, this.State));

    [Fact]
    public void InvokeFunctionToolNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string externalInputStep = InvokeFunctionToolExecutor.Steps.ExternalInput(testId);
        string resumeStep = InvokeFunctionToolExecutor.Steps.Resume(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(InvokeFunctionToolExecutor.Steps.ExternalInput)}", externalInputStep);
        Assert.Equal($"{testId}_{nameof(InvokeFunctionToolExecutor.Steps.Resume)}", resumeStep);
    }

    #endregion

    #region ExecuteAsync Tests

    [Fact]
    public async Task InvokeFunctionToolExecuteWithoutApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithoutApprovalAsync),
            functionName: "simple_function",
            requireApproval: false);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithArgumentsAsync),
            functionName: "get_weather",
            argumentKey: "location",
            argumentValue: "Seattle");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithRequireApprovalAsync),
            functionName: "approval_function",
            requireApproval: true);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithEmptyConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithEmptyConversationIdAsync),
            functionName: "test_function",
            conversationId: "");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullArgumentsAsync),
            functionName: "no_args_function",
            argumentKey: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullRequireApprovalAsync),
            functionName: "test_function",
            requireApproval: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullConversationIdAsync),
            functionName: "test_function",
            conversationId: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    #endregion

    #region CaptureResponseAsync Tests

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithNoOutputConfiguredAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithNoOutputConfiguredAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        FunctionResultContent functionResult = new(action.Id, "Result without output");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithEmptyMessagesAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithEmptyMessagesAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Empty response
        ExternalInputResponse response = new([]);

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ConversationId = "TestConversationId";
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithConversationIdAsync),
            functionName: "test_function",
            conversationId: ConversationId);
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        FunctionResultContent functionResult = new(action.Id, "Result for conversation");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithNonMatchingResultAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithNonMatchingResultAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Use a different call ID that doesn't match the action ID
        FunctionResultContent functionResult = new("different_call_id", "Different result");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithMultipleFunctionResultsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithMultipleFunctionResultsAsync),
            functionName: "test_function",
            conversationId: "TestConversation");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Multiple function results - the matching one should be captured
        FunctionResultContent nonMatchingResult = new("other_call_id", "Other result");
        FunctionResultContent matchingResult = new(action.Id, "Matching result");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [nonMatchingResult, matchingResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    #endregion

    #region Approval Snapshot Security Tests

    /// <summary>
    /// Verifies that mutating the function-name variable after approval does not change
    /// which function is actually invoked. The originally-approved name must be used.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolCaptureResponseUsesApprovedFunctionNameNotMutatedAsync()
    {
        // Arrange
        const string ApprovedFunctionName = "safe_readonly_query";
        const string MutatedFunctionName = "dangerous_admin_tool";

        this.State.Set("TargetFunction", FormulaValue.New(ApprovedFunctionName));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModelWithVariableFunctionName(
            displayName: nameof(InvokeFunctionToolCaptureResponseUsesApprovedFunctionNameNotMutatedAsync),
            variableName: "TargetFunction");

        string? capturedFunctionName = null;
        TestFunctionAgentProvider testAgentProvider = new(
            [
                AIFunctionFactory.Create(() => "safe-result", name: ApprovedFunctionName),
                AIFunctionFactory.Create(() => "dangerous-result", name: MutatedFunctionName),
            ],
            onInvoke: name => capturedFunctionName = name);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("TargetFunction", FormulaValue.New(MutatedFunctionName));
        this.State.Bind();

        // User clicks approve (they saw "safe_readonly_query" in the approval UI)
        ExternalInputResponse response = CreateApprovalResponse(action.Id, approved: true);

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved function must be invoked, not the mutated one
        Assert.NotNull(capturedFunctionName);
        Assert.Equal(ApprovedFunctionName, capturedFunctionName);
    }

    /// <summary>
    /// Verifies that mutating an argument variable after approval does not change
    /// the arguments actually passed to the invoked function.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolCaptureResponseUsesApprovedArgumentsNotMutatedAsync()
    {
        // Arrange
        const string FunctionName = "process_query";
        const string ArgumentKey = "query";
        const string ApprovedQuery = "SELECT * FROM users LIMIT 10";
        const string MutatedQuery = "DROP TABLE users CASCADE; --";

        this.State.Set("SqlQuery", FormulaValue.New(ApprovedQuery));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModelWithVariableArgument(
            displayName: nameof(InvokeFunctionToolCaptureResponseUsesApprovedArgumentsNotMutatedAsync),
            functionName: FunctionName,
            argumentKey: ArgumentKey,
            variableName: "SqlQuery");

        AIFunctionArguments? capturedArguments = null;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create((string query) => $"executed:{query}", name: FunctionName)],
            onInvokeArguments: args => capturedArguments = args);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("SqlQuery", FormulaValue.New(MutatedQuery));
        this.State.Bind();

        // User clicks approve
        ExternalInputResponse response = CreateApprovalResponse(action.Id, approved: true);

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved argument must be used, not the mutated one
        Assert.NotNull(capturedArguments);
        Assert.Equal(ApprovedQuery, capturedArguments[ArgumentKey]?.ToString());
    }

    /// <summary>
    /// Verifies that the approval snapshot survives a checkpoint/restore cycle.
    /// After restore, the originally-approved function must still be used even if state was mutated.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolCaptureResponseUsesSnapshotAfterCheckpointRestoreAsync()
    {
        // Arrange
        const string ApprovedFunctionName = "safe_readonly_query";
        const string MutatedFunctionName = "dangerous_admin_tool";

        this.State.Set("TargetFunction", FormulaValue.New(ApprovedFunctionName));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModelWithVariableFunctionName(
            displayName: nameof(InvokeFunctionToolCaptureResponseUsesSnapshotAfterCheckpointRestoreAsync),
            variableName: "TargetFunction");

        string? capturedFunctionName = null;
        TestFunctionAgentProvider testAgentProvider = new(
            [
                AIFunctionFactory.Create(() => "safe-result", name: ApprovedFunctionName),
                AIFunctionFactory.Create(() => "dangerous-result", name: MutatedFunctionName),
            ],
            onInvoke: name => capturedFunctionName = name);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate checkpoint: persist to state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);

        // Simulate restore on a "new" executor instance by clearing the in-memory field via reflection
        // (In production, a new executor instance would be created with _approvalSnapshot == null)
        typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshot", BindingFlags.NonPublic | BindingFlags.Instance)!
            .SetValue(action, null);

        // Restore from state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);

        // Mutate state after restore (simulating parallel branch)
        this.State.Set("TargetFunction", FormulaValue.New(MutatedFunctionName));
        this.State.Bind();

        // User clicks approve
        ExternalInputResponse response = CreateApprovalResponse(action.Id, approved: true);

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved function must be invoked, not the mutated one
        Assert.NotNull(capturedFunctionName);
        Assert.Equal(ApprovedFunctionName, capturedFunctionName);
    }

    /// <summary>
    /// Verifies that the approval snapshot is cleared after a completed approval cycle,
    /// both in-memory and in the persisted state store. This prevents stale data from
    /// influencing a subsequent execution of the same executor instance.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolCaptureResponseClearsSnapshotAfterCompletionAsync()
    {
        // Arrange
        const string FunctionName = "any_function";

        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseClearsSnapshotAfterCompletionAsync),
            functionName: FunctionName,
            requireApproval: true);

        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "result", name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        // Act - run the full approval cycle
        Dictionary<string, object?> stateStore = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Sanity: snapshot was captured
        FieldInfo snapshotField = typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshot", BindingFlags.NonPublic | BindingFlags.Instance)!;
        Assert.NotNull(snapshotField.GetValue(action));

        ExternalInputResponse response = CreateApprovalResponse(action.Id, approved: true);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - both in-memory field and persisted state are cleared
        Assert.Null(snapshotField.GetValue(action));
        Assert.True(stateStore.ContainsKey("_approvalSnapshot"));
        Assert.Null(stateStore["_approvalSnapshot"]);
    }

    private static ExternalInputResponse CreateApprovalResponse(string actionId, bool approved)
    {
        FunctionCallContent functionCall = new(callId: actionId, name: "ignored");
        ToolApprovalRequestContent approvalRequest = new(actionId, functionCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved);
        return new ExternalInputResponse(new ChatMessage(ChatRole.User, [approvalResponse]));
    }

    private static Mock<IWorkflowContext> CreateMockWorkflowContext()
    {
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        return mockContext;
    }

    /// <summary>
    /// Creates a mock workflow context that actually stores state values (for checkpoint/restore tests).
    /// Optionally accepts an externally-owned dictionary so callers can inspect the persisted state.
    /// </summary>
    private static Mock<IWorkflowContext> CreateMockWorkflowContextWithStateStore(Dictionary<string, object?>? stateStore = null)
    {
        stateStore ??= [];
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<ApprovalSnapshot?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<string, ApprovalSnapshot?, string?, CancellationToken>((key, value, _, _) => stateStore[key] = value)
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.ReadStateAsync<ApprovalSnapshot>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns<string, string?, CancellationToken>((key, _, _) =>
                new ValueTask<ApprovalSnapshot?>(stateStore.TryGetValue(key, out object? val) ? val as ApprovalSnapshot : null));
        mockContext.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new HashSet<string>());
        return mockContext;
    }

    /// <summary>
    /// Invokes a protected method on the executor via reflection (for testing checkpoint hooks).
    /// </summary>
    private static async ValueTask InvokeProtectedMethodAsync(InvokeFunctionToolExecutor action, string methodName, IWorkflowContext context, CancellationToken cancellationToken)
    {
        MethodInfo method = typeof(InvokeFunctionToolExecutor)
            .GetMethod(methodName, BindingFlags.NonPublic | BindingFlags.Instance)!;
        ValueTask result = (ValueTask)method.Invoke(action, [context, cancellationToken])!;
        await result.ConfigureAwait(false);
    }

    /// <summary>
    /// Minimal concrete <see cref="ResponseAgentProvider"/> that exposes an injected
    /// <see cref="AIFunction"/> registry and records which function got invoked.
    /// Used by the framework-invoke approval branch (<c>InvokeRegisteredFunctionAsync</c>).
    /// </summary>
    private sealed class TestFunctionAgentProvider : ResponseAgentProvider
    {
        private readonly Action<string>? _onInvoke;
        private readonly Action<AIFunctionArguments>? _onInvokeArguments;

        public TestFunctionAgentProvider(
            IEnumerable<AIFunction> functions,
            Action<string>? onInvoke = null,
            Action<AIFunctionArguments>? onInvokeArguments = null)
        {
            this._onInvoke = onInvoke;
            this._onInvokeArguments = onInvokeArguments;
            this.Functions = functions.Select(f => (AIFunction)new RecordingAIFunction(f, this)).ToList();
        }

        internal void RecordInvocation(string name, AIFunctionArguments? arguments)
        {
            this._onInvoke?.Invoke(name);
            if (arguments is not null)
            {
                this._onInvokeArguments?.Invoke(arguments);
            }
        }

        public override Task<string> CreateConversationAsync(CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override IAsyncEnumerable<AgentResponseUpdate> InvokeAgentAsync(
            string agentId, string? agentVersion, string? conversationId,
            IEnumerable<ChatMessage>? messages, IDictionary<string, object?>? inputArguments,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override IAsyncEnumerable<ChatMessage> GetMessagesAsync(
            string conversationId, int? limit = null, string? after = null, string? before = null,
            bool newestFirst = false, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        private sealed class RecordingAIFunction(AIFunction inner, TestFunctionAgentProvider owner) : AIFunction
        {
            public override string Name => inner.Name;
            public override string Description => inner.Description;
            public override JsonElement JsonSchema => inner.JsonSchema;

            protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
            {
                owner.RecordInvocation(inner.Name, arguments);
                return inner.InvokeAsync(arguments, cancellationToken);
            }
        }
    }

    #endregion

    #region Helper Methods

    private async Task ExecuteTestAsync(InvokeFunctionTool model)
    {
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // IsDiscreteAction should be false for InvokeFunction
        VerifyIsDiscrete(action, isDiscrete: false);
    }

    private async Task<WorkflowEvent[]> ExecuteCaptureResponseTestAsync(
        InvokeFunctionToolExecutor action,
        ExternalInputResponse response)
    {
        return await this.ExecuteAsync(
            action,
            InvokeFunctionToolExecutor.Steps.ExternalInput(action.Id),
            (context, _, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));
    }

    private InvokeFunctionTool CreateModel(
        string displayName,
        string functionName,
        bool? requireApproval = false,
        string? conversationId = null,
        string? argumentKey = null,
        string? argumentValue = null)
    {
        InvokeFunctionTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            FunctionName = new StringExpression.Builder(StringExpression.Literal(functionName)),
            RequireApproval = requireApproval != null ? new BoolExpression.Builder(BoolExpression.Literal(requireApproval.Value)) : null
        };

        if (conversationId is not null)
        {
            builder.ConversationId = new StringExpression.Builder(StringExpression.Literal(conversationId));
        }

        if (argumentKey is not null && argumentValue is not null)
        {
            builder.Arguments.Add(argumentKey, ValueExpression.Literal(new StringDataValue(argumentValue)));
        }

        return AssignParent<InvokeFunctionTool>(builder);
    }

    private InvokeFunctionTool CreateModelWithVariableFunctionName(string displayName, string variableName)
    {
        InvokeFunctionTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            FunctionName = new StringExpression.Builder(
                StringExpression.Variable(PropertyPath.TopicVariable(variableName))),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(true)),
        };
        return AssignParent<InvokeFunctionTool>(builder);
    }

    private InvokeFunctionTool CreateModelWithVariableArgument(
        string displayName, string functionName, string argumentKey, string variableName)
    {
        InvokeFunctionTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            FunctionName = new StringExpression.Builder(StringExpression.Literal(functionName)),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(true)),
        };
        builder.Arguments.Add(argumentKey,
            ValueExpression.Variable(PropertyPath.TopicVariable(variableName)));
        return AssignParent<InvokeFunctionTool>(builder);
    }

    #endregion
}
