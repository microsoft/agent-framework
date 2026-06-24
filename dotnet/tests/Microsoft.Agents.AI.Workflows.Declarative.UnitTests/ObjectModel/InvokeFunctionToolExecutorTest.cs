// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
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

        // Act - trigger ExecuteAsync to emit the approval request
        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("TargetFunction", FormulaValue.New(MutatedFunctionName));
        this.State.Bind();

        // User clicks approve (they saw "safe_readonly_query" in the approval UI)
        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);

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

        // Act - trigger ExecuteAsync to emit the approval request
        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("SqlQuery", FormulaValue.New(MutatedQuery));
        this.State.Bind();

        // User clicks approve
        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);

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

        // Act - trigger ExecuteAsync to emit the approval request and capture the snapshot
        List<ExternalInputRequest> emittedRequests = [];
        Dictionary<string, object?> stateStore = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore, emittedRequests);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate checkpoint: persist to state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);

        // Simulate restore on a "new" executor instance by clearing the in-memory dictionary via reflection
        ConcurrentDictionary<string, ApprovalSnapshot> liveSnapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(action)!;
        liveSnapshots.Clear();

        // Restore from state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);

        // Mutate state after restore (simulating parallel branch)
        this.State.Set("TargetFunction", FormulaValue.New(MutatedFunctionName));
        this.State.Bind();

        // User clicks approve
        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved function must be invoked, not the mutated one
        Assert.NotNull(capturedFunctionName);
        Assert.Equal(ApprovedFunctionName, capturedFunctionName);
    }

    /// <summary>
    /// Verifies that the approval snapshot entry is removed after a completed approval cycle.
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
        List<ExternalInputRequest> emittedRequests = [];
        Dictionary<string, object?> stateStore = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore, emittedRequests);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Sanity: snapshot dict has exactly one entry
        FieldInfo snapshotsField = typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!;
        ConcurrentDictionary<string, ApprovalSnapshot> snapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)snapshotsField.GetValue(action)!;
        Assert.Single(snapshots);

        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - in-memory dict is empty after the matching response is captured
        Assert.Empty(snapshots);
    }

    /// <summary>
    /// Each ExecuteAsync invocation must produce a unique per-invocation request id on
    /// both the FunctionCallContent.CallId and the ToolApprovalRequestContent.RequestId.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolEmitsUniqueRequestIdPerInvocationAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolEmitsUniqueRequestIdPerInvocationAsync),
            functionName: "any_function",
            requireApproval: true);
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "result", name: "any_function")]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);

        // Act - emit two approval requests from the same executor instance
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Assert - two distinct request ids surfaced
        Assert.Equal(2, emittedRequests.Count);
        string id1 = emittedRequests[0].AgentResponse.Messages
            .SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().Single().RequestId;
        string id2 = emittedRequests[1].AgentResponse.Messages
            .SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().Single().RequestId;
        Assert.NotEqual(id1, id2);
        Assert.NotEqual(action.Id, id1);
        Assert.NotEqual(action.Id, id2);

        // And the matching inner FunctionCallContent uses the same id
        FunctionCallContent fcc1 = emittedRequests[0].AgentResponse.Messages
            .SelectMany(m => m.Contents).OfType<FunctionCallContent>().Single();
        Assert.Equal(id1, fcc1.CallId);
    }

    /// <summary>
    /// Two concurrent pending approvals on the same executor must each resume with their
    /// own approved arguments — out-of-order responses must not swap which invocation gets
    /// which set of arguments.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolConcurrentPendingApprovalsDoNotSwapAsync()
    {
        // Arrange
        const string FunctionName = "process_query";
        const string ArgumentKey = "query";
        const string ArgumentsA = "A-args";
        const string ArgumentsB = "B-args";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolConcurrentPendingApprovalsDoNotSwapAsync),
            functionName: FunctionName,
            requireApproval: true,
            argumentKey: ArgumentKey,
            argumentValue: ArgumentsA);
        InvokeFunctionTool modelB = this.CreateModel(
            displayName: nameof(InvokeFunctionToolConcurrentPendingApprovalsDoNotSwapAsync) + "B",
            functionName: FunctionName,
            requireApproval: true,
            argumentKey: ArgumentKey,
            argumentValue: ArgumentsB);

        List<string?> capturedQueries = [];
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create((string query) => $"executed:{query}", name: FunctionName)],
            onInvokeArguments: args => capturedQueries.Add(args[ArgumentKey]?.ToString()));

        // Two executor instances simulating concurrent fan-in scenarios with different YAML-evaluated args
        InvokeFunctionToolExecutor actionA = new(model, testAgentProvider, this.State);
        InvokeFunctionToolExecutor actionB = new(modelB, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedA = [];
        List<ExternalInputRequest> emittedB = [];
        Mock<IWorkflowContext> ctxA = CreateMockWorkflowContext(emittedA);
        Mock<IWorkflowContext> ctxB = CreateMockWorkflowContext(emittedB);

        // Act - both executors emit approval requests
        await actionA.HandleAsync(new ActionExecutorResult(actionA.Id), ctxA.Object, CancellationToken.None);
        await actionB.HandleAsync(new ActionExecutorResult(actionB.Id), ctxB.Object, CancellationToken.None);

        // Deliver responses out of order: B first, then A
        await actionB.CaptureResponseAsync(ctxB.Object, CreateApprovalResponseFor(emittedB, approved: true), CancellationToken.None);
        await actionA.CaptureResponseAsync(ctxA.Object, CreateApprovalResponseFor(emittedA, approved: true), CancellationToken.None);

        // Assert - each invocation executed with its own approved arguments
        Assert.Equal([ArgumentsB, ArgumentsA], capturedQueries);
    }

    /// <summary>
    /// When the approval response references a request id that is not in the snapshot map,
    /// the executor must surface a structured error and must not invoke any function.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolMissingSnapshotReturnsStructuredErrorAsync()
    {
        // Arrange
        const string FunctionName = "any_function";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolMissingSnapshotReturnsStructuredErrorAsync),
            functionName: FunctionName,
            requireApproval: true);

        bool functionWasInvoked = false;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => { functionWasInvoked = true; return "result"; }, name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();

        // Act - deliver an approval response whose RequestId has no matching snapshot
        FunctionCallContent fcc = new(callId: "stale-id", name: FunctionName);
        ToolApprovalRequestContent staleRequest = new("stale-id", fcc);
        ToolApprovalResponseContent staleResponse = staleRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [staleResponse]));

        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the registered function must NOT have been invoked. The
        // ToolApprovalResponseContent.RequestId did not match any snapshot in the executor's
        // map, so the executor does not attempt to invoke the function at all (no silent
        // state re-evaluation).
        Assert.False(functionWasInvoked);
    }

    /// <summary>
    /// Two non-approval invocations of the same executor must emit distinct per-invocation
    /// CallIds so each response is matched to its originating request.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolNonApprovalCallIdsAreDistinctPerInvocationAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolNonApprovalCallIdsAreDistinctPerInvocationAsync),
            functionName: "any_function",
            requireApproval: false);
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "result", name: "any_function")]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);

        // Act - emit two non-approval function-call requests
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Assert - distinct CallIds were stamped on the two emitted FunctionCallContents
        Assert.Equal(2, emittedRequests.Count);
        FunctionCallContent fcc1 = emittedRequests[0].AgentResponse.Messages
            .SelectMany(m => m.Contents).OfType<FunctionCallContent>().Single();
        FunctionCallContent fcc2 = emittedRequests[1].AgentResponse.Messages
            .SelectMany(m => m.Contents).OfType<FunctionCallContent>().Single();
        Assert.NotEqual(fcc1.CallId, fcc2.CallId);
        Assert.NotEqual(action.Id, fcc1.CallId);
        Assert.NotEqual(action.Id, fcc2.CallId);
    }

    /// <summary>
    /// A snapshot persisted at the legacy <c>"_approvalSnapshot"</c> key must be migrated
    /// under <c>this.Id</c> after restore so an approval response carrying
    /// <c>RequestId == this.Id</c> resumes with the snapshot's arguments.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolLegacySingleSnapshotCheckpointIsMigratedAsync()
    {
        // Arrange
        const string FunctionName = "any_function";
        const string ArgumentKey = "query";
        const string LegacyApprovedArg = "legacy-approved";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolLegacySingleSnapshotCheckpointIsMigratedAsync),
            functionName: FunctionName,
            requireApproval: true);

        AIFunctionArguments? capturedArguments = null;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create((string query) => $"executed:{query}", name: FunctionName)],
            onInvokeArguments: args => capturedArguments = args);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        // Seed the state store with a single ApprovalSnapshot at the legacy key.
        Dictionary<string, object?> stateStore = new()
        {
            ["_approvalSnapshot"] = new ApprovalSnapshot(
                FunctionName,
                new Dictionary<string, object?> { [ArgumentKey] = LegacyApprovedArg }),
        };
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore);

        // Act - restore migrates the legacy snapshot under this.Id.
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);

        ConcurrentDictionary<string, ApprovalSnapshot> snapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(action)!;
        Assert.True(snapshots.ContainsKey(action.Id));

        // Deliver an approval response with RequestId == action.Id and resume.
        FunctionCallContent fcc = new(callId: action.Id, name: FunctionName);
        ToolApprovalRequestContent legacyRequest = new(action.Id, fcc);
        ToolApprovalResponseContent legacyResponse = legacyRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [legacyResponse]));

        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the function was invoked with the snapshot arguments.
        Assert.NotNull(capturedArguments);
        Assert.Equal(LegacyApprovedArg, capturedArguments[ArgumentKey]?.ToString());
    }

    /// <summary>
    /// The legacy <c>"_approvalSnapshot"</c> key is removed from the state store after
    /// migration so subsequent checkpoints do not carry stale data.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolLegacyKeyIsClearedAfterMigrationAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolLegacyKeyIsClearedAfterMigrationAsync),
            functionName: "any_function",
            requireApproval: true);
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "result", name: "any_function")]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        Dictionary<string, object?> stateStore = new()
        {
            ["_approvalSnapshot"] = new ApprovalSnapshot("any_function", new Dictionary<string, object?>()),
        };
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore);

        // Act
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);

        // Assert - legacy key was cleared via QueueStateUpdateAsync<ApprovalSnapshot?>(null).
        Assert.False(stateStore.ContainsKey("_approvalSnapshot"));
    }

    /// <summary>
    /// Drives ExecuteAsync → checkpoint → ResetAsync → restore → CaptureResponseAsync on a
    /// single pending approval and asserts the originally-approved arguments are used,
    /// even though ResetAsync cleared the in-memory dict between checkpoint and restore.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolResumeAfterResetUsesPersistedSnapshotAsync()
    {
        // Arrange
        const string FunctionName = "process_query";
        const string ArgumentKey = "query";
        const string ApprovedQuery = "SELECT * FROM users LIMIT 10";

        this.State.Set("SqlQuery", FormulaValue.New(ApprovedQuery));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModelWithVariableArgument(
            displayName: nameof(InvokeFunctionToolResumeAfterResetUsesPersistedSnapshotAsync),
            functionName: FunctionName,
            argumentKey: ArgumentKey,
            variableName: "SqlQuery");

        AIFunctionArguments? capturedArguments = null;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create((string query) => $"executed:{query}", name: FunctionName)],
            onInvokeArguments: args => capturedArguments = args);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Dictionary<string, object?> stateStore = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore, emittedRequests);

        ConcurrentDictionary<string, ApprovalSnapshot> liveSnapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(action)!;

        // Act - emit, checkpoint, reset (simulates runner end), restore, then capture.
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);
        await action.ResetAsync();
        Assert.Empty(liveSnapshots);

        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);
        Assert.Single(liveSnapshots);

        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved argument was used and the entry was removed.
        Assert.NotNull(capturedArguments);
        Assert.Equal(ApprovedQuery, capturedArguments[ArgumentKey]?.ToString());
        Assert.Empty(liveSnapshots);
    }

    /// <summary>
    /// Two pending invocations (A then B) are interleaved with checkpoint/reset/restore
    /// cycles; A's snapshot must survive both reset cycles and route A's response to
    /// A's arguments, while B remains pending and is later resolved correctly.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolMultiplePendingInvocationsSurviveCheckpointResetRestoreAsync()
    {
        // Arrange
        const string FunctionName = "process_query";
        const string ArgumentKey = "query";
        const string ArgumentsA = "A-args";
        const string ArgumentsB = "B-args";

        this.State.Set("SqlQuery", FormulaValue.New(ArgumentsA));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeFunctionTool model = this.CreateModelWithVariableArgument(
            displayName: nameof(InvokeFunctionToolMultiplePendingInvocationsSurviveCheckpointResetRestoreAsync),
            functionName: FunctionName,
            argumentKey: ArgumentKey,
            variableName: "SqlQuery");

        List<string?> capturedQueries = [];
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create((string query) => $"executed:{query}", name: FunctionName)],
            onInvokeArguments: args => capturedQueries.Add(args[ArgumentKey]?.ToString()));
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Dictionary<string, object?> stateStore = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore(stateStore, emittedRequests);

        ConcurrentDictionary<string, ApprovalSnapshot> liveSnapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(action)!;

        // Act - invocation A with ArgumentsA, then full checkpoint/reset/restore.
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);
        await action.ResetAsync();
        Assert.Empty(liveSnapshots);
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);
        Assert.Single(liveSnapshots);

        // Mutate the source variable, then invocation B with ArgumentsB.
        this.State.Set("SqlQuery", FormulaValue.New(ArgumentsB));
        this.State.Bind();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);
        await action.ResetAsync();
        Assert.Empty(liveSnapshots);
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);
        Assert.Equal(2, liveSnapshots.Count);

        // Capture A's response. State has been mutated to ArgumentsB but the per-invocation
        // snapshot must still drive invocation with ArgumentsA.
        Assert.Equal(2, emittedRequests.Count);
        ExternalInputResponse responseA = CreateApprovalResponseForRequest(emittedRequests[0], approved: true);
        await action.CaptureResponseAsync(mockContext.Object, responseA, CancellationToken.None);
        Assert.Single(liveSnapshots);
        Assert.Equal([ArgumentsA], capturedQueries);

        // Another checkpoint/reset/restore cycle - B's snapshot survives.
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);
        await action.ResetAsync();
        Assert.Empty(liveSnapshots);
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);
        Assert.Single(liveSnapshots);

        // Capture B's response.
        ExternalInputResponse responseB = CreateApprovalResponseForRequest(emittedRequests[1], approved: true);
        await action.CaptureResponseAsync(mockContext.Object, responseB, CancellationToken.None);

        // Assert - both invocations executed with their own approved arguments; nothing pending.
        Assert.Equal([ArgumentsA, ArgumentsB], capturedQueries);
        Assert.Empty(liveSnapshots);
    }

    /// <summary>
    /// An approval response whose RequestId does not match any pending snapshot must
    /// NOT invoke the function and must assign a not-approved error to Output.Result.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolUnmatchedApprovalAssignsErrorAsync()
    {
        // Arrange
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolUnmatchedApprovalAssignsErrorAsync),
            functionName: FunctionName,
            requireApproval: true,
            outputResultVariable: ResultVariable);

        bool functionWasInvoked = false;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => { functionWasInvoked = true; return "result"; }, name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();

        // Act - deliver an approval response whose RequestId has no matching snapshot.
        FunctionCallContent fcc = new(callId: "stale-id", name: FunctionName);
        ToolApprovalRequestContent staleRequest = new("stale-id", fcc);
        ToolApprovalResponseContent staleResponse = staleRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [staleResponse]));

        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - function was NOT invoked AND the error string landed at Output.Result.
        Assert.False(functionWasInvoked);
        Assert.Contains(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value.Contains("No pending approval"));
    }

    /// <summary>
    /// An approval response whose RequestId matches a pending snapshot but is
    /// Approved == false must NOT invoke the function, must remove the snapshot, and
    /// must assign a not-approved error to Output.Result.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolRejectedApprovalAssignsErrorAsync()
    {
        // Arrange
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolRejectedApprovalAssignsErrorAsync),
            functionName: FunctionName,
            requireApproval: true,
            outputResultVariable: ResultVariable);

        bool functionWasInvoked = false;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => { functionWasInvoked = true; return "result"; }, name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);

        ConcurrentDictionary<string, ApprovalSnapshot> liveSnapshots = (ConcurrentDictionary<string, ApprovalSnapshot>)typeof(InvokeFunctionToolExecutor)
            .GetField("_approvalSnapshots", BindingFlags.NonPublic | BindingFlags.Instance)!
            .GetValue(action)!;

        // Act - emit the approval request, then deliver a rejection for it.
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        Assert.Single(liveSnapshots);

        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: false);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - function not invoked, snapshot removed, error assigned.
        Assert.False(functionWasInvoked);
        Assert.Empty(liveSnapshots);
        Assert.Contains(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value.Contains("not approved by user"));
    }

    /// <summary>
    /// When a response contains multiple <see cref="ToolApprovalResponseContent"/> items —
    /// e.g. an unrelated / stale approval followed by the valid one — the executor must
    /// select the approval whose RequestId matches a pending snapshot and invoke the
    /// function, not silently drop the valid approval because a stale one appeared first.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolApprovalMatchPrefersPendingSnapshotAsync()
    {
        // Arrange
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolApprovalMatchPrefersPendingSnapshotAsync),
            functionName: FunctionName,
            requireApproval: true,
            outputResultVariable: ResultVariable);

        bool functionWasInvoked = false;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => { functionWasInvoked = true; return "result"; }, name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);

        // Emit one valid approval request from this executor.
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);
        ExternalInputRequest emitted = Assert.Single(emittedRequests);
        ToolApprovalRequestContent validRequest = emitted.AgentResponse.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .Single();

        // Build a batched response: a stale (unrelated) approval first, then the valid one.
        ToolApprovalRequestContent staleRequest = new("stale-id", new FunctionCallContent("stale-id", FunctionName));
        ToolApprovalResponseContent staleResponse = staleRequest.CreateResponse(approved: true);
        ToolApprovalResponseContent validResponse = validRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [staleResponse, validResponse]));

        // Act
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the valid approval drove invocation; no error was assigned.
        Assert.True(functionWasInvoked);
        Assert.DoesNotContain(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value.StartsWith("Error:", StringComparison.Ordinal));
    }

    /// <summary>
    /// Delivering the same approval response twice must invoke the registered function
    /// exactly once; the second delivery surfaces the not-approved error path because the
    /// snapshot has already been consumed.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolDuplicateApprovalDeliveryInvokesFunctionOnceAsync()
    {
        // Arrange
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolDuplicateApprovalDeliveryInvokesFunctionOnceAsync),
            functionName: FunctionName,
            requireApproval: true,
            outputResultVariable: ResultVariable);

        int invocationCount = 0;
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => { Interlocked.Increment(ref invocationCount); return "result"; }, name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);

        // Emit one approval request.
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Act - deliver the SAME approval response twice.
        ExternalInputResponse response = CreateApprovalResponseFor(emittedRequests, approved: true);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the registered AIFunction was invoked exactly once.
        Assert.Equal(1, invocationCount);
        // The second delivery surfaced the no-pending-approval error.
        Assert.Contains(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value.Contains("No pending approval"));
    }

    /// <summary>
    /// A non-approval <c>FunctionResultContent</c> whose CallId equals <c>this.Id</c> is
    /// consumed and assigned to <c>Output.Result</c> when no pendings are tracked.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolLegacyNonApprovalResultIsAcceptedAsync()
    {
        // Arrange - a fresh executor has no tracked pendings.
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";
        const string HostResult = "host-computed-result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolLegacyNonApprovalResultIsAcceptedAsync),
            functionName: FunctionName,
            requireApproval: false,
            outputResultVariable: ResultVariable);
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "should-not-be-called", name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();

        // Act - deliver a FunctionResultContent with CallId == action.Id.
        FunctionResultContent legacyResult = new(action.Id, HostResult);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [legacyResult]));

        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the host-computed result was assigned to Output.Result and no
        // error was emitted.
        Assert.Contains(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value == HostResult);
        Assert.DoesNotContain(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value.StartsWith("Error:", StringComparison.Ordinal));
    }

    /// <summary>
    /// The legacy non-approval backstop must NOT fire when the executor has a tracked
    /// pending invocation; a <c>FunctionResultContent</c> with <c>CallId == this.Id</c>
    /// is rejected in that state.
    /// </summary>
    [Fact]
    public async Task InvokeFunctionToolLegacyNonApprovalBackstopGatedOnEmptyStateAsync()
    {
        // Arrange - emit a non-approval call so a per-invocation CallId is tracked.
        const string FunctionName = "any_function";
        const string ResultVariable = "Result";

        this.State.InitializeSystem();
        this.State.Bind();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolLegacyNonApprovalBackstopGatedOnEmptyStateAsync),
            functionName: FunctionName,
            requireApproval: false,
            outputResultVariable: ResultVariable);
        TestFunctionAgentProvider testAgentProvider = new(
            [AIFunctionFactory.Create(() => "result", name: FunctionName)]);
        InvokeFunctionToolExecutor action = new(model, testAgentProvider, this.State);

        List<ExternalInputRequest> emittedRequests = [];
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext(emittedRequests);
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Act - deliver a FunctionResultContent with CallId == action.Id (not the emitted GUID).
        FunctionResultContent staleLegacyResult = new(action.Id, "should-be-rejected");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [staleLegacyResult]));

        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - Output.Result was NOT assigned with the rejected result.
        Assert.DoesNotContain(mockContext.Invocations, i =>
            i.Method.Name == nameof(IWorkflowContext.QueueStateUpdateAsync)
            && i.Arguments.Count >= 2
            && i.Arguments[1] is StringValue sv
            && sv.Value == "should-be-rejected");
    }

    /// <summary>
    /// Builds an approval response paired to the inner <c>ToolApprovalRequestContent.RequestId</c>
    /// of a specific emitted request. Used when multiple requests are emitted and the
    /// caller needs to address one by position.
    /// </summary>
    private static ExternalInputResponse CreateApprovalResponseForRequest(ExternalInputRequest emitted, bool approved)
    {
        ToolApprovalRequestContent approvalRequest = emitted.AgentResponse.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .Single();
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved);
        return new ExternalInputResponse(new ChatMessage(ChatRole.User, [approvalResponse]));
    }

    /// <summary>
    /// Extracts the inner <c>ToolApprovalRequestContent.RequestId</c> from the
    /// approval request the executor emitted, and builds a paired response. This mirrors
    /// the framework's symmetric content-id rewriting at the envelope boundary.
    /// </summary>
    private static ExternalInputResponse CreateApprovalResponseFor(IReadOnlyList<ExternalInputRequest> emittedRequests, bool approved)
    {
        ExternalInputRequest emitted = Assert.Single(emittedRequests);
        return CreateApprovalResponseForRequest(emitted, approved);
    }

    private static Mock<IWorkflowContext> CreateMockWorkflowContext(List<ExternalInputRequest>? emittedRequests = null)
    {
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<object, string?, CancellationToken>((msg, _, _) =>
            {
                if (emittedRequests is not null && msg is ExternalInputRequest request)
                {
                    emittedRequests.Add(request);
                }
            })
            .Returns(default(ValueTask));
        return mockContext;
    }

    /// <summary>
    /// Creates a mock workflow context that actually stores state values (for checkpoint/restore tests).
    /// Optionally accepts an externally-owned dictionary so callers can inspect the persisted state,
    /// and an optional emitted-request list so tests can build matching responses.
    /// </summary>
    private static Mock<IWorkflowContext> CreateMockWorkflowContextWithStateStore(
        Dictionary<string, object?>? stateStore = null,
        List<ExternalInputRequest>? emittedRequests = null)
    {
        stateStore ??= [];
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<Dictionary<string, ApprovalSnapshot>>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<string, Dictionary<string, ApprovalSnapshot>, string?, CancellationToken>((key, value, _, _) => stateStore[key] = value)
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<List<string>>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<string, List<string>, string?, CancellationToken>((key, value, _, _) => stateStore[key] = value)
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<ApprovalSnapshot?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<string, ApprovalSnapshot?, string?, CancellationToken>((key, value, _, _) =>
            {
                if (value is null)
                {
                    stateStore.Remove(key);
                }
                else
                {
                    stateStore[key] = value;
                }
            })
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<object, string?, CancellationToken>((msg, _, _) =>
            {
                if (emittedRequests is not null && msg is ExternalInputRequest request)
                {
                    emittedRequests.Add(request);
                }
            })
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.ReadStateAsync<Dictionary<string, ApprovalSnapshot>>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns<string, string?, CancellationToken>((key, _, _) =>
                new ValueTask<Dictionary<string, ApprovalSnapshot>?>(stateStore.TryGetValue(key, out object? val) ? val as Dictionary<string, ApprovalSnapshot> : null));
        mockContext.Setup(c => c.ReadStateAsync<List<string>>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns<string, string?, CancellationToken>((key, _, _) =>
                new ValueTask<List<string>?>(stateStore.TryGetValue(key, out object? val) ? val as List<string> : null));
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
        string? argumentValue = null,
        string? outputResultVariable = null)
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

        if (outputResultVariable is not null)
        {
            builder.Output = new InvokeToolOutput.Builder
            {
                Result = new InitializablePropertyPath(PropertyPath.TopicVariable(outputResultVariable), isInitializer: false),
            };
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
