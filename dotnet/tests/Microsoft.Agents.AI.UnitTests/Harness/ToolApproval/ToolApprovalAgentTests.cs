// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ToolApprovalAgent"/> class.
/// </summary>
public class ToolApprovalAgentTests
{
    #region Constructor

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerAgent is null.
    /// </summary>
    [Fact]
    public void Constructor_NullInnerAgent_ThrowsAsync()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () => new ToolApprovalAgent(null!));
    }

    /// <summary>
    /// Verify that constructor creates a valid instance.
    /// </summary>
    [Fact]
    public void Constructor_ValidInnerAgent_CreatesInstanceAsync()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;

        // Act
        var agent = new ToolApprovalAgent(innerAgent);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that constructor accepts custom JsonSerializerOptions.
    /// </summary>
    [Fact]
    public void Constructor_CustomJsonSerializerOptions_CreatesInstanceAsync()
    {
        // Arrange
        var innerAgent = new Mock<AIAgent>().Object;
        var options = new JsonSerializerOptions();

        // Act
        var agent = new ToolApprovalAgent(innerAgent, options);

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region RunAsync - Passthrough

    /// <summary>
    /// Verify that when there are no approval requests, response passes through unchanged.
    /// </summary>
    [Fact]
    public async Task RunAsync_NoApprovalRequests_PassesThroughAsync()
    {
        // Arrange
        var expectedResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Hello")]);
        var innerAgent = CreateMockAgent(expectedResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatClientAgentSession());

        // Assert
        Assert.Equal("Hello", response.Text);
    }

    /// <summary>
    /// Verify that approval requests with no matching rules are surfaced to the caller.
    /// </summary>
    [Fact]
    public async Task RunAsync_ApprovalRequestNoRule_SurfacesToCallerAsync()
    {
        // Arrange
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var responseMessage = new ChatMessage(ChatRole.Assistant, [approvalRequest]);
        var expectedResponse = new AgentResponse([responseMessage]);
        var innerAgent = CreateMockAgent(expectedResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatClientAgentSession());

        // Assert
        var requests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("MyTool", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    #endregion

    #region RunAsync - Deferred Auto-Approve

    /// <summary>
    /// Verify that when a tool-level rule exists, matching approval requests are
    /// auto-approved immediately and the inner agent is re-called in the same run.
    /// </summary>
    [Fact]
    public async Task RunAsync_ToolLevelRule_DeferredAutoApproveAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));

        // Call 1: establish rule + inner agent returns approval request → auto-approved → re-call inner agent
        var approvalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [approvalRequest])]);
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Done")]);

        var callCount = 0;
        List<ChatMessage>? secondCallMessages = null;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
            {
                callCount++;
                if (callCount == 2)
                {
                    secondCallMessages = msgs.ToList();
                }
            })
            .ReturnsAsync(() => callCount == 1 ? approvalResponse : finalResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: send always-approve → establishes rule, inner returns TARc → auto-approved → re-calls inner
        var alwaysApproveResponse = approvalRequest.CreateAlwaysApproveToolResponse("User said always");
        var response1 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApproveResponse])],
            session);

        // Assert — inner agent was called twice within the same RunAsync call
        Assert.Equal(2, callCount);
        Assert.Equal("Done", response1.Text);

        // Response should NOT surface the auto-approved approval request to caller
        var surfacedRequests = response1.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Empty(surfacedRequests);

        // Verify that the re-call received the injected auto-approval response
        Assert.NotNull(secondCallMessages);
        var injectedApprovals = secondCallMessages!.SelectMany(m => m.Contents).OfType<ToolApprovalResponseContent>().ToList();
        Assert.Single(injectedApprovals);
        Assert.True(injectedApprovals[0].Approved);
    }

    /// <summary>
    /// Verify that a tool+arguments rule stores pending auto-approvals for matching calls.
    /// </summary>
    [Fact]
    public async Task RunAsync_ToolWithArgsRule_DeferredAutoApproveAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var args = new Dictionary<string, object?> { ["path"] = "test.txt" };
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ReadFile", args));
        var approvalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [approvalRequest])]);
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "File content")]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() =>
            {
                callCount++;
                return callCount == 1 ? approvalResponse : finalResponse;
            });

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: set up the rule
        var alwaysApproveResponse = approvalRequest.CreateAlwaysApproveToolWithArgumentsResponse();
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApproveResponse])],
            session);

        // Call 2: pending auto-approval injected
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Continue")],
            session);

        // Assert
        Assert.Equal("File content", response.Text);
    }

    /// <summary>
    /// Verify that a tool+arguments rule does NOT auto-approve when arguments differ.
    /// </summary>
    [Fact]
    public async Task RunAsync_ToolWithArgsRule_DoesNotAutoApproveDifferentArgsAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();

        // Set up rule with args { path: "test.txt" }
        var ruleArgs = new Dictionary<string, object?> { ["path"] = "test.txt" };
        var ruleRequest = new ToolApprovalRequestContent("req0", new FunctionCallContent("call0", "ReadFile", ruleArgs));
        var alwaysApproveResponse = ruleRequest.CreateAlwaysApproveToolWithArgumentsResponse();

        // Then the inner agent returns an approval for DIFFERENT args
        var differentArgs = new Dictionary<string, object?> { ["path"] = "other.txt" };
        var newApprovalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ReadFile", differentArgs));
        var approvalResponseMsg = new AgentResponse([new ChatMessage(ChatRole.Assistant, [newApprovalRequest])]);

        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(approvalResponseMsg);

        var agent = new ToolApprovalAgent(innerAgent.Object);
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, [alwaysApproveResponse]),
        };

        // Act
        var response = await agent.RunAsync(inputMessages, session);

        // Assert — the approval request should surface to the caller (not auto-approved)
        var requests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ReadFile", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    #endregion

    #region Mixed Auto-Approve

    /// <summary>
    /// Verify that when some approval requests match rules and others don't,
    /// matching ones are stored as pending and non-matching are surfaced.
    /// </summary>
    [Fact]
    public async Task RunAsync_MixedApprovalRequests_SurfacesNonMatchingStoreMatchingAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();

        // Set up a rule for ToolA only
        var ruleRequest = new ToolApprovalRequestContent("rule-req", new FunctionCallContent("rule-call", "ToolA"));
        var alwaysApprove = ruleRequest.CreateAlwaysApproveToolResponse();

        // Inner agent returns approval requests for both ToolA and ToolB
        var approvalA = new ToolApprovalRequestContent("reqA", new FunctionCallContent("callA", "ToolA"));
        var approvalB = new ToolApprovalRequestContent("reqB", new FunctionCallContent("callB", "ToolB"));
        var mixedResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [approvalA, approvalB])]);

        var innerAgent = CreateMockAgent(mixedResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: establish rule + get mixed approval response
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Assert — ToolB request surfaced to caller, ToolA auto-approved is removed from response
        var surfacedRequests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(surfacedRequests);
        Assert.Equal("ToolB", ((FunctionCallContent)surfacedRequests[0].ToolCall).Name);

        // Call 2: verify pending auto-approval for ToolA is injected
        List<ChatMessage>? capturedMessages = null;
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Final")]);
        var callCount = 0;
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
            {
                callCount++;
                capturedMessages = msgs.ToList();
            })
            .ReturnsAsync(finalResponse);

        // User manually approves ToolB and sends along
        var toolBApproval = approvalB.CreateResponse(approved: true);
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [toolBApproval])],
            session);

        // Verify pending auto-approval for ToolA was injected
        Assert.NotNull(capturedMessages);
        var allApprovals = capturedMessages!.SelectMany(m => m.Contents).OfType<ToolApprovalResponseContent>().ToList();
        Assert.Equal(2, allApprovals.Count); // ToolA auto-approval + ToolB manual approval
    }

    #endregion

    #region Content Ordering

    /// <summary>
    /// Verify that content ordering is preserved when unwrapping AlwaysApproveToolApprovalResponseContent.
    /// </summary>
    [Fact]
    public async Task RunAsync_UnwrapPreservesContentOrderAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();

        // Message with mixed content: text before, always-approve in middle, text after
        var textBefore = new TextContent("Before");
        var textAfter = new TextContent("After");
        var inputMessage = new ChatMessage(ChatRole.User, [textBefore, alwaysApprove, textAfter]);

        List<ChatMessage>? capturedMessages = null;
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);

        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
                capturedMessages = msgs.ToList())
            .ReturnsAsync(finalResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        await agent.RunAsync([inputMessage], session);

        // Assert — content order should be: TextContent("Before"), ToolApprovalResponseContent, TextContent("After")
        Assert.NotNull(capturedMessages);
        var contents = capturedMessages![0].Contents;
        Assert.Equal(3, contents.Count);
        Assert.IsType<TextContent>(contents[0]);
        Assert.Equal("Before", ((TextContent)contents[0]).Text);
        Assert.IsType<ToolApprovalResponseContent>(contents[1]);
        Assert.IsType<TextContent>(contents[2]);
        Assert.Equal("After", ((TextContent)contents[2]).Text);
    }

    #endregion

    #region Unwrapping

    /// <summary>
    /// Verify that AlwaysApproveToolApprovalResponseContent is unwrapped to the inner ToolApprovalResponseContent
    /// before being forwarded to the inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_UnwrapsAlwaysApproveResponse_ForwardsInnerResponseAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();

        List<ChatMessage>? capturedMessages = null;
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);

        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
                capturedMessages = msgs.ToList())
            .ReturnsAsync(finalResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, [alwaysApprove]),
        };

        // Act
        await agent.RunAsync(inputMessages, session);

        // Assert — the forwarded message should contain ToolApprovalResponseContent, not AlwaysApproveToolApprovalResponseContent
        Assert.NotNull(capturedMessages);
        var contents = capturedMessages!.SelectMany(m => m.Contents).ToList();
        Assert.DoesNotContain(contents, c => c is AlwaysApproveToolApprovalResponseContent);
        Assert.Contains(contents, c => c is ToolApprovalResponseContent);
    }

    #endregion

    #region Rule Persistence

    /// <summary>
    /// Verify that rules persist across multiple RunAsync calls on the same session,
    /// and that auto-approved TARc are immediately handled via re-call within the same run.
    /// </summary>
    [Fact]
    public async Task RunAsync_RulesPersistAcrossCallsAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();

        // Call 1: no approval requests in response, just establish the rule
        var firstResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);
        // Call 2a: return an approval request that should match stored rule → auto-approved → re-call
        var secondApproval = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "MyTool"));
        var secondResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [secondApproval])]);
        // Call 2b: re-call after auto-approve, final response
        var thirdResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Done after auto-approve")]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() =>
            {
                callCount++;
                return callCount switch
                {
                    1 => firstResponse,
                    2 => secondResponse,
                    _ => thirdResponse,
                };
            });

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: establish rule (no approval requests returned)
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Call 2: inner agent returns TARc → matches rule → auto-approved → re-call → final response
        var response2 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session);

        // Assert — inner agent called 3 times total (1 for rule setup, 2 for auto-approve loop)
        Assert.Equal("Done after auto-approve", response2.Text);
        Assert.Equal(3, callCount);
    }

    /// <summary>
    /// Verify that collected approval responses are cleared after injection (during the loop re-call).
    /// A subsequent RunAsync call should not inject them again.
    /// </summary>
    [Fact]
    public async Task RunAsync_CollectedApprovalResponses_ClearedAfterInjectionAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();

        // Call 1: establish rule
        var firstResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);
        // Call 2a: return approval → auto-approved → loop
        var approval = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "MyTool"));
        var secondResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [approval])]);
        // Call 2b: re-call after auto-approve (injected)
        var thirdResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Injected")]);
        // Call 3: no pending (already cleared by the loop)
        var fourthResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Clean")]);

        var callCount = 0;
        List<ChatMessage>? lastCallMessages = null;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
            {
                callCount++;
                lastCallMessages = msgs.ToList();
            })
            .ReturnsAsync(() => callCount switch
            {
                1 => firstResponse,
                2 => secondResponse,
                3 => thirdResponse,
                _ => fourthResponse,
            });

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: establish rule (callCount → 1)
        await agent.RunAsync([new ChatMessage(ChatRole.User, [alwaysApprove])], session);

        // Call 2: inner returns TARc → auto-approved → loop → callCount → 2, 3
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Trigger approval")], session);

        // Call 3: no pending (cleared by the loop), callCount → 4
        var response3 = await agent.RunAsync([new ChatMessage(ChatRole.User, "No pending")], session);

        // Assert — last call should only have the user message, no injected approvals
        Assert.NotNull(lastCallMessages);
        var approvals = lastCallMessages!.SelectMany(m => m.Contents).OfType<ToolApprovalResponseContent>().ToList();
        Assert.Empty(approvals);
        Assert.Equal("Clean", response3.Text);
    }

    #endregion

    #region RunStreamingAsync

    /// <summary>
    /// Verify that streaming passthrough works when there are no approval requests.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_NoApprovalRequests_PassesThroughAsync()
    {
        // Arrange
        var updates = new[] { new AgentResponseUpdate(ChatRole.Assistant, "Hello") };
        var innerAgent = CreateMockStreamingAgent(updates);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var results = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatClientAgentSession()))
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Equal("Hello", results[0].Text);
    }

    #endregion

    #region MatchesRule

    /// <summary>
    /// Verify that a tool-level rule matches regardless of arguments.
    /// </summary>
    [Fact]
    public void MatchesRule_ToolLevelRule_MatchesAnyArgs()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new() { ToolName = "MyTool" },
        };
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "MyTool", new Dictionary<string, object?> { ["x"] = "1" }));

        // Act & Assert
        Assert.True(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that a tool-level rule does not match a different tool name.
    /// </summary>
    [Fact]
    public void MatchesRule_ToolLevelRule_DoesNotMatchDifferentTool()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new() { ToolName = "ToolA" },
        };
        var request = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolB"));

        // Act & Assert
        Assert.False(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that a tool+arguments rule matches with exact same arguments.
    /// </summary>
    [Fact]
    public void MatchesRule_ToolWithArgsRule_MatchesExactArgs()
    {
        // Arrange — rule arguments must be in serialized form (JSON string representation)
        var rules = new List<ToolApprovalRule>
        {
            new()
            {
                ToolName = "ReadFile",
                Arguments = new Dictionary<string, string> { ["path"] = "\"test.txt\"" },
            },
        };
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "ReadFile", new Dictionary<string, object?> { ["path"] = "test.txt" }));

        // Act & Assert
        Assert.True(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that a tool+arguments rule does not match when argument values differ.
    /// </summary>
    [Fact]
    public void MatchesRule_ToolWithArgsRule_DoesNotMatchDifferentValues()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new()
            {
                ToolName = "ReadFile",
                Arguments = new Dictionary<string, string> { ["path"] = "\"test.txt\"" },
            },
        };
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "ReadFile", new Dictionary<string, object?> { ["path"] = "other.txt" }));

        // Act & Assert
        Assert.False(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that a tool+arguments rule does not match when argument count differs.
    /// </summary>
    [Fact]
    public void MatchesRule_ToolWithArgsRule_DoesNotMatchDifferentArgCount()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new()
            {
                ToolName = "ReadFile",
                Arguments = new Dictionary<string, string> { ["path"] = "\"test.txt\"" },
            },
        };
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "ReadFile", new Dictionary<string, object?>
            {
                ["path"] = "test.txt",
                ["encoding"] = "utf-8",
            }));

        // Act & Assert
        Assert.False(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that a non-FunctionCallContent tool call does not match any rule.
    /// </summary>
    [Fact]
    public void MatchesRule_NonFunctionCallContent_ReturnsFalse()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new() { ToolName = "MyTool" },
        };
        var request = new ToolApprovalRequestContent("req1", new ToolCallContent("call1"));

        // Act & Assert
        Assert.False(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    /// <summary>
    /// Verify that matching works with JsonElement argument values.
    /// </summary>
    [Fact]
    public void MatchesRule_JsonElementArgs_MatchesCorrectly()
    {
        // Arrange
        var rules = new List<ToolApprovalRule>
        {
            new()
            {
                ToolName = "MyTool",
                Arguments = new Dictionary<string, string> { ["count"] = "42" },
            },
        };
        var jsonElement = JsonDocument.Parse("42").RootElement;
        var request = new ToolApprovalRequestContent("req1",
            new FunctionCallContent("call1", "MyTool", new Dictionary<string, object?> { ["count"] = jsonElement }));

        // Act & Assert
        Assert.True(ToolApprovalAgent.MatchesRule(request, rules, AgentJsonUtilities.DefaultOptions));
    }

    #endregion

    #region Extension Methods

    /// <summary>
    /// Verify that CreateAlwaysApproveToolResponse creates the correct wrapper.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_SetsCorrectFlags()
    {
        // Arrange
        var request = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));

        // Act
        var result = request.CreateAlwaysApproveToolResponse("Test reason");

        // Assert
        Assert.True(result.AlwaysApproveTool);
        Assert.False(result.AlwaysApproveToolWithArguments);
        Assert.True(result.InnerResponse.Approved);
        Assert.Equal("Test reason", result.InnerResponse.Reason);
        Assert.Equal("req1", result.InnerResponse.RequestId);
    }

    /// <summary>
    /// Verify that CreateAlwaysApproveToolWithArgumentsResponse creates the correct wrapper.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_SetsCorrectFlags()
    {
        // Arrange
        var request = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));

        // Act
        var result = request.CreateAlwaysApproveToolWithArgumentsResponse();

        // Assert
        Assert.False(result.AlwaysApproveTool);
        Assert.True(result.AlwaysApproveToolWithArguments);
        Assert.True(result.InnerResponse.Approved);
    }

    /// <summary>
    /// Verify that extension methods throw on null request.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolResponse_NullRequest_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("request",
            () => ((ToolApprovalRequestContent)null!).CreateAlwaysApproveToolResponse());
    }

    /// <summary>
    /// Verify that extension methods throw on null request.
    /// </summary>
    [Fact]
    public void CreateAlwaysApproveToolWithArgumentsResponse_NullRequest_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("request",
            () => ((ToolApprovalRequestContent)null!).CreateAlwaysApproveToolWithArgumentsResponse());
    }

    #endregion

    #region Duplicate Rule Prevention

    /// <summary>
    /// Verify that sending the same always-approve response twice does not create duplicate rules.
    /// </summary>
    [Fact]
    public async Task RunAsync_DuplicateAlwaysApprove_DoesNotDuplicateRuleAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var request1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var request2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "MyTool"));

        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);
        var innerAgent = CreateMockAgent(finalResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act — send two always-approve responses for the same tool
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [request1.CreateAlwaysApproveToolResponse()])],
            session);
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [request2.CreateAlwaysApproveToolResponse()])],
            session);

        // Assert — verify the state works correctly (rule still matches on subsequent call)
        var thirdApproval = new ToolApprovalRequestContent("req3", new FunctionCallContent("call3", "MyTool"));
        var approvalResponseMsg = new AgentResponse([new ChatMessage(ChatRole.Assistant, [thirdApproval])]);
        var afterAutoResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Auto-approved")]);

        var callCount = 0;
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() =>
            {
                callCount++;
                return callCount == 1 ? approvalResponseMsg : afterAutoResponse;
            });

        // Call 3: triggers approval → stored as pending
        await agent.RunAsync([new ChatMessage(ChatRole.User, "test")], session);

        // Call 4: pending injected
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "continue")], session);
        Assert.Equal("Auto-approved", response.Text);
    }

    #endregion

    #region Auto-Approved Removal

    /// <summary>
    /// Verify that auto-approved requests are removed from the non-streaming response
    /// and the inner agent is re-called, returning actual content.
    /// </summary>
    [Fact]
    public async Task RunAsync_AutoApprovedRequest_RemovedFromResponseAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();

        // Inner agent returns a TARc on first call, then real content on second
        var approvalResponseContent = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "MyTool"));
        var firstResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [approvalResponseContent])]);
        var secondResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Tool executed successfully")]);

        var innerAgent = new Mock<AIAgent>();
        var callCount = 0;
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() => ++callCount == 1 ? firstResponse : secondResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act: establish rule + inner returns matching approval request → auto-approved → re-call
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Assert — auto-approved request removed, inner agent called twice, final response has text
        var allRequests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Empty(allRequests);
        Assert.Equal("Tool executed successfully", response.Messages[0].Text);
        Assert.Equal(2, callCount);
    }

    /// <summary>
    /// Verify that auto-approved requests are removed from streaming updates
    /// and the inner agent is re-called, yielding actual content.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_AutoApprovedRequest_RemovedFromUpdatesAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));

        // First establish a rule via non-streaming
        var alwaysApprove = approvalRequest.CreateAlwaysApproveToolResponse();
        var setupResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);

        var innerAgent = new Mock<AIAgent>();

        // Setup non-streaming for rule establishment
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(setupResponse);

        // First streaming call: text + auto-approvable TARc. Second call: just text (tool executed).
        var streamApproval = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "MyTool"));
        var textUpdate = new AgentResponseUpdate(ChatRole.Assistant, "Hello");
        var approvalUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { streamApproval });
        var finalUpdate = new AgentResponseUpdate(ChatRole.Assistant, "Done");

        var streamCallCount = 0;
        innerAgent
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ++streamCallCount == 1
                ? ToAsyncEnumerableAsync(new[] { textUpdate, approvalUpdate })
                : ToAsyncEnumerableAsync(new[] { finalUpdate }));

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Establish the rule
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Act — stream with auto-approvable request
        var results = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session))
        {
            results.Add(update);
        }

        // Assert — text from first call + final text from re-call; no TARc surfaced
        Assert.Equal(2, results.Count);
        Assert.Equal("Hello", results[0].Text);
        Assert.Equal("Done", results[1].Text);
        Assert.Equal(2, streamCallCount);
    }

    /// <summary>
    /// Verify that non-matching approval requests remain in streaming updates.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_NonMatchingRequest_SurfacedToCallerAsync()
    {
        // Arrange
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "UnknownTool"));
        var approvalUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { approvalRequest });

        var innerAgent = CreateMockStreamingAgent([approvalUpdate]);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var results = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatClientAgentSession()))
        {
            results.Add(update);
        }

        // Assert — non-matching request should be surfaced
        Assert.Single(results);
        var requests = results[0].Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("UnknownTool", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that a message with only auto-approved content is removed from the response
    /// when the inner agent is re-called after auto-approving.
    /// </summary>
    [Fact]
    public async Task RunAsync_MessageWithOnlyAutoApprovedContent_RemovedEntirelyAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var ruleRequest = new ToolApprovalRequestContent("rule-req", new FunctionCallContent("rule-call", "MyTool"));
        var alwaysApprove = ruleRequest.CreateAlwaysApproveToolResponse();

        // First call: returns TARc-only message + text message. Second call: returns just text (tools executed).
        var approvalContent = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var approvalMessage = new ChatMessage(ChatRole.Assistant, [approvalContent]);
        var textMessage = new ChatMessage(ChatRole.Assistant, "Final text");
        var firstResponse = new AgentResponse([approvalMessage, textMessage]);
        var secondResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Tools executed")]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() => ++callCount == 1 ? firstResponse : secondResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Assert — inner agent re-called after auto-approve, final response from second call
        Assert.Equal(2, callCount);
        Assert.Single(response.Messages);
        Assert.Equal("Tools executed", response.Messages[0].Text);
    }

    /// <summary>
    /// Verify that a streaming update with mixed content (auto-approved + non-auto-approved) only removes the auto-approved part.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_MixedUpdate_OnlyRemovesAutoApprovedAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var ruleRequest = new ToolApprovalRequestContent("rule-req", new FunctionCallContent("rule-call", "ToolA"));
        var alwaysApprove = ruleRequest.CreateAlwaysApproveToolResponse();

        // Setup non-streaming for rule establishment
        var setupResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "OK")]);
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(setupResponse);

        // Streaming update with both auto-approvable (ToolA) and non-auto-approvable (ToolB) requests
        var autoApprovable = new ToolApprovalRequestContent("reqA", new FunctionCallContent("callA", "ToolA"));
        var notAutoApprovable = new ToolApprovalRequestContent("reqB", new FunctionCallContent("callB", "ToolB"));
        var mixedUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { autoApprovable, notAutoApprovable });

        innerAgent
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(ToAsyncEnumerableAsync(new[] { mixedUpdate }));

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Establish rule
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        // Act
        var results = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session))
        {
            results.Add(update);
        }

        // Assert — only ToolB request should remain
        Assert.Single(results);
        var requests = results[0].Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolB", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    #endregion

    #region Queue Behavior - Non-Streaming

    /// <summary>
    /// Verify that when the inner agent returns multiple unapproved TARc, only the first is returned
    /// and the rest are queued.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleTARc_ReturnsOnlyFirstAsync()
    {
        // Arrange
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));
        var tarc3 = new ToolApprovalRequestContent("req3", new FunctionCallContent("call3", "ToolC"));
        var innerResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc1, tarc2, tarc3])]);
        var innerAgent = CreateMockAgent(innerResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            new ChatClientAgentSession());

        // Assert — only the first TARc should be returned
        var requests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolA", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that after approving the first queued item, the second is returned on the next call
    /// without calling the inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_ApproveFirst_ReturnsSecondFromQueueAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));
        var tarc3 = new ToolApprovalRequestContent("req3", new FunctionCallContent("call3", "ToolC"));
        var innerResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc1, tarc2, tarc3])]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((_, _, _, _) => callCount++)
            .ReturnsAsync(innerResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc
        var response1 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session);

        // Call 2: approve first, get second from queue
        var approval1 = tarc1.CreateResponse(approved: true, reason: "OK");
        var response2 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [approval1])],
            session);

        // Assert — second TARc returned, inner agent called only once
        Assert.Equal(1, callCount);
        var requests = response2.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolB", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that "always approve" on the first queued item auto-approves matching items in the queue.
    /// </summary>
    [Fact]
    public async Task RunAsync_AlwaysApproveFirst_AutoApprovesMatchingInQueueAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();

        // Three TARc: two for ToolA (different args), one for ToolB
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA", arguments: new Dictionary<string, object?> { ["q"] = "query1" }));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolA", arguments: new Dictionary<string, object?> { ["q"] = "query2" }));
        var tarc3 = new ToolApprovalRequestContent("req3", new FunctionCallContent("call3", "ToolB"));

        var innerResponse1 = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc1, tarc2, tarc3])]);
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Done")]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((_, _, _, _) => callCount++)
            .ReturnsAsync(() => callCount == 1 ? innerResponse1 : finalResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc (ToolA query1)
        var response1 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session);

        Assert.Single(response1.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>());

        // Call 2: always approve ToolA → should auto-approve ToolA query2 in queue, return ToolB
        var alwaysApprove = tarc1.CreateAlwaysApproveToolResponse("Always approve ToolA");
        var response2 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session);

        var requests2 = response2.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests2);
        Assert.Equal("ToolB", ((FunctionCallContent)requests2[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that once all queued items are resolved, the inner agent is called with all collected responses.
    /// </summary>
    [Fact]
    public async Task RunAsync_AllQueuedResolved_CallsInnerAgentWithCollectedResponsesAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));

        var innerResponse1 = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc1, tarc2])]);
        var finalResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "All tools executed")]);

        var callCount = 0;
        List<ChatMessage>? thirdCallMessages = null;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, _) =>
            {
                callCount++;
                if (callCount == 2)
                {
                    thirdCallMessages = msgs.ToList();
                }
            })
            .ReturnsAsync(() => callCount == 1 ? innerResponse1 : finalResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session);

        // Call 2: approve first, get second from queue
        var approval1 = tarc1.CreateResponse(approved: true, reason: "OK");
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [approval1])],
            session);

        // Call 3: approve second → queue empty → inner agent called
        var approval2 = tarc2.CreateResponse(approved: true, reason: "OK");
        var response3 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [approval2])],
            session);

        // Assert — inner agent called twice (initial + after queue resolved)
        Assert.Equal(2, callCount);
        Assert.Equal("All tools executed", response3.Text);

        // Verify collected responses were injected
        Assert.NotNull(thirdCallMessages);
        var injectedResponses = thirdCallMessages!.SelectMany(m => m.Contents).OfType<ToolApprovalResponseContent>().ToList();
        Assert.Equal(2, injectedResponses.Count);
    }

    /// <summary>
    /// Verify that a single TARc (no excess) is returned without queueing.
    /// </summary>
    [Fact]
    public async Task RunAsync_SingleTARc_NoQueueingAsync()
    {
        // Arrange
        var tarc = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "MyTool"));
        var innerResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc])]);
        var innerAgent = CreateMockAgent(innerResponse);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            new ChatClientAgentSession());

        // Assert — single TARc returned directly
        var requests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("MyTool", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that denying a queued item collects the denial and proceeds to the next.
    /// </summary>
    [Fact]
    public async Task RunAsync_DenyFirst_ReturnsSecondFromQueueAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));
        var innerResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, [tarc1, tarc2])]);

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((_, _, _, _) => callCount++)
            .ReturnsAsync(innerResponse);

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc
        await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Do something")],
            session);

        // Call 2: deny first, get second from queue
        var denial = tarc1.CreateResponse(approved: false, reason: "No");
        var response2 = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, [denial])],
            session);

        // Assert — second TARc returned, inner agent called only once
        Assert.Equal(1, callCount);
        var requests = response2.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolB", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    #endregion

    #region Queue Behavior - Streaming

    /// <summary>
    /// Verify that when streaming yields multiple unapproved TARc, only the first is yielded.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_MultipleTARc_YieldsOnlyFirstAsync()
    {
        // Arrange
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));
        var approvalUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { tarc1, tarc2 });
        var textUpdate = new AgentResponseUpdate(ChatRole.Assistant, "Searching...");

        var innerAgent = CreateMockStreamingAgent([textUpdate, approvalUpdate]);
        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Act
        var results = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Search")],
            new ChatClientAgentSession()))
        {
            results.Add(update);
        }

        // Assert — text update + one TARc
        Assert.Equal(2, results.Count);
        Assert.Equal("Searching...", results[0].Text);
        var requests = results[1].Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolA", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    /// <summary>
    /// Verify that streaming returns queued items one at a time on subsequent calls.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ApproveFirst_ReturnsSecondFromQueueAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolB"));
        var approvalUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { tarc1, tarc2 });

        var callCount = 0;
        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((_, _, _, _) => callCount++)
            .Returns(ToAsyncEnumerableAsync(new[] { approvalUpdate }));

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc
        var results1 = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Search")],
            session))
        {
            results1.Add(update);
        }

        Assert.Single(results1);
        Assert.Equal("ToolA", ((FunctionCallContent)results1[0].Contents.OfType<ToolApprovalRequestContent>().Single().ToolCall).Name);

        // Call 2: approve first, get second from queue
        var approval = tarc1.CreateResponse(approved: true, reason: "OK");
        var results2 = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, [approval])],
            session))
        {
            results2.Add(update);
        }

        // Assert — second TARc returned from queue, inner agent called only once
        Assert.Equal(1, callCount);
        Assert.Single(results2);
        Assert.Equal("ToolB", ((FunctionCallContent)results2[0].Contents.OfType<ToolApprovalRequestContent>().Single().ToolCall).Name);
    }

    /// <summary>
    /// Verify that "always approve" during streaming queue auto-approves matching items.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_AlwaysApproveFirst_AutoApprovesMatchingInQueueAsync()
    {
        // Arrange
        var session = new ChatClientAgentSession();

        // Two ToolA calls + one ToolB call
        var tarc1 = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ToolA"));
        var tarc2 = new ToolApprovalRequestContent("req2", new FunctionCallContent("call2", "ToolA"));
        var tarc3 = new ToolApprovalRequestContent("req3", new FunctionCallContent("call3", "ToolB"));
        var approvalUpdate = new AgentResponseUpdate(ChatRole.Assistant, new List<AIContent> { tarc1, tarc2, tarc3 });

        var innerAgent = new Mock<AIAgent>();
        innerAgent
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(ToAsyncEnumerableAsync(new[] { approvalUpdate }));

        var agent = new ToolApprovalAgent(innerAgent.Object);

        // Call 1: get first TARc (ToolA)
        var results1 = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, "Search")],
            session))
        {
            results1.Add(update);
        }

        // Call 2: always approve ToolA → second ToolA auto-approved, returns ToolB
        var alwaysApprove = tarc1.CreateAlwaysApproveToolResponse();
        var results2 = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(
            [new ChatMessage(ChatRole.User, [alwaysApprove])],
            session))
        {
            results2.Add(update);
        }

        // Assert — ToolB returned (ToolA[2] was auto-approved)
        Assert.Single(results2);
        var requests = results2[0].Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(requests);
        Assert.Equal("ToolB", ((FunctionCallContent)requests[0].ToolCall).Name);
    }

    #endregion

    #region Helpers

    private static Mock<AIAgent> CreateMockAgent(AgentResponse response)
    {
        var mock = new Mock<AIAgent>();
        mock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);
        return mock;
    }

    private static Mock<AIAgent> CreateMockStreamingAgent(AgentResponseUpdate[] updates)
    {
        var mock = new Mock<AIAgent>();
        mock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(ToAsyncEnumerableAsync(updates));
        return mock;
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(
        IEnumerable<T> items,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var item in items)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return item;
            await Task.Yield();
        }
    }

    #endregion
}
