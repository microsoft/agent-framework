// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests that verify the end-to-end approval flow behavior of the
/// <see cref="ChatClientAgent"/> class with <see cref="PerServiceCallChatHistoryPersistingChatClient"/>,
/// ensuring that chat history is correctly persisted across multi-turn approval interactions.
/// </summary>
public class ChatClientAgent_ApprovalsTests
{
    #region Per-Service-Call Persistence Approval Tests

    /// <summary>
    /// Verifies that with per-service-call persistence and an approval-required tool,
    /// a two-turn approval flow persists the correct final history:
    /// Turn 1: user asks → model returns FCC → FICC converts to ToolApprovalRequestContent → returned to caller.
    /// Turn 2: caller sends ToolApprovalResponseContent → FICC processes approval, invokes function, calls model again.
    /// Final history: [user, assistant(FCC), tool(FRC), assistant(final)].
    /// </summary>
    [Fact]
    public async Task RunAsync_ApprovalRequired_PerServiceCallPersistence_PersistsCorrectHistoryAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "Sunny, 22°C", "GetWeather", "Gets the weather");
        var approvalTool = new ApprovalRequiredAIFunction(tool);

        var callIndex = new ChatClientAgentTestHelper.Ref<int>(0);
        var capturedInputs = new List<List<ChatMessage>>();
        var serviceExpectations = new List<ChatClientAgentTestHelper.ServiceCallExpectation>
        {
            // Turn 1: model returns a function call (FICC will convert to approval request)
            new(new ChatResponse([new(ChatRole.Assistant,
                [new FunctionCallContent("call1", "GetWeather", new Dictionary<string, object?> { ["city"] = "Amsterdam" })])])),
            // Turn 2: after approval, FICC invokes the function and calls the model again
            new(new ChatResponse([new(ChatRole.Assistant, "The weather in Amsterdam is sunny and 22°C.")])),
        };

        // Act — Turn 1: initial request
        var result1 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: [new(ChatRole.User, "What's the weather?")],
            serviceCallExpectations: serviceExpectations,
            agentOptions: new()
            {
                ChatOptions = new() { Tools = [approvalTool] },
                RequirePerServiceCallChatHistoryPersistence = true,
            },
            callIndex: callIndex,
            capturedInputs: capturedInputs);

        // Verify Turn 1 returns exactly one approval request
        var approvalRequests = result1.Response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .ToList();
        Assert.Single(approvalRequests);
        Assert.Equal(1, result1.TotalServiceCalls);

        // Verify service received user message on first call
        Assert.Single(capturedInputs);
        Assert.Contains(capturedInputs[0], m => m.Role == ChatRole.User && m.Text == "What's the weather?");

        // Act — Turn 2: send approval response
        var approvalResponseMessages = approvalRequests.ConvertAll(req =>
            new ChatMessage(ChatRole.User, [req.CreateResponse(approved: true)]));

        await ChatClientAgentTestHelper.RunAsync(
            inputMessages: approvalResponseMessages,
            serviceCallExpectations: serviceExpectations,
            existingSession: result1.Session,
            existingAgent: result1.Agent,
            existingMock: result1.MockService,
            callIndex: callIndex,
            capturedInputs: capturedInputs,
            expectedServiceCallCount: 2,
            expectedHistory:
            [
                new(ChatRole.User, TextContains: "What's the weather?"),
                new(ChatRole.Assistant, ContentTypes: [typeof(FunctionCallContent)]),
                new(ChatRole.Tool, ContentTypes: [typeof(FunctionResultContent)]),
                new(ChatRole.Assistant, TextContains: "sunny and 22°C"),
            ]);

        // Verify second service call received the full conversation (user + FCC + FRC)
        Assert.Equal(2, capturedInputs.Count);
        Assert.Contains(capturedInputs[1], m => m.Contents.OfType<FunctionCallContent>().Any());
        Assert.Contains(capturedInputs[1], m => m.Contents.OfType<FunctionResultContent>().Any());
    }

    #endregion

    #region End-of-Run Persistence Approval Tests

    /// <summary>
    /// Verifies that with end-of-run persistence and an approval-required tool,
    /// a two-turn approval flow persists the correct final history.
    /// </summary>
    [Fact]
    public async Task RunAsync_ApprovalRequired_EndOfRunPersistence_PersistsCorrectHistoryAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "Sunny, 22°C", "GetWeather", "Gets the weather");
        var approvalTool = new ApprovalRequiredAIFunction(tool);

        var callIndex = new ChatClientAgentTestHelper.Ref<int>(0);
        var capturedInputs = new List<List<ChatMessage>>();
        var serviceExpectations = new List<ChatClientAgentTestHelper.ServiceCallExpectation>
        {
            new(new ChatResponse([new(ChatRole.Assistant,
                [new FunctionCallContent("call1", "GetWeather", new Dictionary<string, object?> { ["city"] = "Amsterdam" })])])),
            new(new ChatResponse([new(ChatRole.Assistant, "The weather in Amsterdam is sunny and 22°C.")])),
        };

        // Act — Turn 1
        var result1 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: [new(ChatRole.User, "What's the weather?")],
            serviceCallExpectations: serviceExpectations,
            agentOptions: new()
            {
                ChatOptions = new() { Tools = [approvalTool] },
            },
            callIndex: callIndex,
            capturedInputs: capturedInputs);

        var approvalRequests = result1.Response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .ToList();
        Assert.Single(approvalRequests);

        // Act — Turn 2
        var approvalResponseMessages = approvalRequests.ConvertAll(req =>
            new ChatMessage(ChatRole.User, [req.CreateResponse(approved: true)]));

        var result2 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: approvalResponseMessages,
            serviceCallExpectations: serviceExpectations,
            existingSession: result1.Session,
            existingAgent: result1.Agent,
            existingMock: result1.MockService,
            callIndex: callIndex,
            capturedInputs: capturedInputs,
            expectedServiceCallCount: 2,
            expectedHistory:
            [
                // End-of-run persistence retains the approval request from Turn 1
                // and the approval response from Turn 2
                new(ChatRole.User, TextContains: "What's the weather?"),
                new(ChatRole.Assistant, ContentTypes: [typeof(ToolApprovalRequestContent)]),
                new(ChatRole.User, ContentTypes: [typeof(ToolApprovalResponseContent)]),
                new(ChatRole.Assistant, ContentTypes: [typeof(FunctionCallContent)]),
                new(ChatRole.Tool, ContentTypes: [typeof(FunctionResultContent)]),
                new(ChatRole.Assistant, TextContains: "sunny and 22°C"),
            ]);
    }

    #endregion

    #region Service-Stored History Approval Tests

    /// <summary>
    /// Verifies that with service-stored history (ConversationId returned) and an approval-required tool,
    /// the two-turn approval flow completes without errors and the session gets the ConversationId.
    /// </summary>
    [Fact]
    public async Task RunAsync_ApprovalRequired_ServiceStoredHistory_CompletesWithoutErrorAsync()
    {
        // Arrange
        const string ConversationId = "thread-456";
        var tool = AIFunctionFactory.Create(() => "Sunny, 22°C", "GetWeather", "Gets the weather");
        var approvalTool = new ApprovalRequiredAIFunction(tool);

        var callIndex = new ChatClientAgentTestHelper.Ref<int>(0);
        var capturedInputs = new List<List<ChatMessage>>();
        var serviceExpectations = new List<ChatClientAgentTestHelper.ServiceCallExpectation>
        {
            new(new ChatResponse([new(ChatRole.Assistant,
                [new FunctionCallContent("call1", "GetWeather", new Dictionary<string, object?> { ["city"] = "Amsterdam" })])])
            {
                ConversationId = ConversationId,
            }),
            new(new ChatResponse([new(ChatRole.Assistant, "The weather in Amsterdam is sunny and 22°C.")])
            {
                ConversationId = ConversationId,
            }),
        };

        // Act — Turn 1
        var result1 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: [new(ChatRole.User, "What's the weather?")],
            serviceCallExpectations: serviceExpectations,
            agentOptions: new()
            {
                ChatOptions = new() { Tools = [approvalTool] },
            },
            callIndex: callIndex,
            capturedInputs: capturedInputs);

        var approvalRequests = result1.Response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .ToList();
        Assert.Single(approvalRequests);
        Assert.Equal(ConversationId, result1.Session.ConversationId);

        // Act — Turn 2
        var approvalResponseMessages = approvalRequests.ConvertAll(req =>
            new ChatMessage(ChatRole.User, [req.CreateResponse(approved: true)]));

        var result2 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: approvalResponseMessages,
            serviceCallExpectations: serviceExpectations,
            existingSession: result1.Session,
            existingAgent: result1.Agent,
            existingMock: result1.MockService,
            callIndex: callIndex,
            capturedInputs: capturedInputs,
            expectedServiceCallCount: 2);

        // Assert — session should retain the ConversationId, response should be correct
        Assert.Equal(ConversationId, result2.Session.ConversationId);
        Assert.Contains(result2.Response.Messages, m => m.Text == "The weather in Amsterdam is sunny and 22°C.");
    }

    #endregion

    #region Approval Rejected Tests

    /// <summary>
    /// Verifies that when an approval is rejected, the rejection result is persisted in the history
    /// and the model receives the rejection information.
    /// </summary>
    [Fact]
    public async Task RunAsync_ApprovalRejected_PersistsRejectionInHistoryAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "Sunny, 22°C", "GetWeather", "Gets the weather");
        var approvalTool = new ApprovalRequiredAIFunction(tool);

        var callIndex = new ChatClientAgentTestHelper.Ref<int>(0);
        var capturedInputs = new List<List<ChatMessage>>();
        var serviceExpectations = new List<ChatClientAgentTestHelper.ServiceCallExpectation>
        {
            // Turn 1: model requests function call
            new(new ChatResponse([new(ChatRole.Assistant,
                [new FunctionCallContent("call1", "GetWeather", new Dictionary<string, object?> { ["city"] = "Amsterdam" })])])),
            // Turn 2: after rejection, model gets the rejection info and responds accordingly
            new(new ChatResponse([new(ChatRole.Assistant, "I'm sorry, I cannot check the weather without your approval.")])),
        };

        // Act — Turn 1
        var result1 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: [new(ChatRole.User, "What's the weather?")],
            serviceCallExpectations: serviceExpectations,
            agentOptions: new()
            {
                ChatOptions = new() { Tools = [approvalTool] },
                RequirePerServiceCallChatHistoryPersistence = true,
            },
            callIndex: callIndex,
            capturedInputs: capturedInputs);

        var approvalRequests = result1.Response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .ToList();
        Assert.Single(approvalRequests);

        // Act — Turn 2: reject the approval
        var rejectionMessages = approvalRequests.ConvertAll(req =>
            new ChatMessage(ChatRole.User, [req.CreateResponse(approved: false, reason: "User declined")]));

        var result2 = await ChatClientAgentTestHelper.RunAsync(
            inputMessages: rejectionMessages,
            serviceCallExpectations: serviceExpectations,
            existingSession: result1.Session,
            existingAgent: result1.Agent,
            existingMock: result1.MockService,
            callIndex: callIndex,
            capturedInputs: capturedInputs,
            expectedServiceCallCount: 2);

        // Assert — history should contain the rejection result (FRC with rejection)
        var history = ChatClientAgentTestHelper.GetPersistedHistory(result2.Agent, result2.Session);
        Assert.True(
            history.Count >= 3,
            $"Expected at least 3 messages in history, got {history.Count}.\n{ChatClientAgentTestHelper.FormatMessages(history)}");
        Assert.Contains(history, m => m.Role == ChatRole.User && m.Text == "What's the weather?");
        Assert.Contains(history, m => m.Contents.OfType<FunctionResultContent>().Any(
            frc => frc.Result?.ToString()?.Contains("rejected") == true));
        Assert.Contains(history, m => m.Role == ChatRole.Assistant &&
            m.Text == "I'm sorry, I cannot check the weather without your approval.");

        // Verify the second service call received the rejection FRC
        Assert.Equal(2, capturedInputs.Count);
        Assert.Contains(capturedInputs[1], m => m.Contents.OfType<FunctionResultContent>().Any(
            frc => frc.Result?.ToString()?.Contains("rejected") == true));
    }

    #endregion
}
