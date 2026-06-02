// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using RootToolApprovalRequestPropagator = Microsoft.Agents.AI.ToolApprovalRequestPropagator;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Tests for nested approval propagation when an <see cref="AIAgent"/> is exposed as an <see cref="AIFunction"/>.
/// </summary>
public sealed class AsAIFunctionApprovalPropagationTests
{
    [Fact]
    public async Task InvokeAsync_WhenChildAgentRequestsApproval_AttachesParentApprovalAndTerminatesAsync()
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var childFunctionCall = new FunctionCallContent("child-call", "SensitiveTool");
        var childApprovalRequest = new ToolApprovalRequestContent("approval-1", childFunctionCall);
        var childSession = new TestAgentSession();

        var childAgent = new TestAIAgent
        {
            RunAsyncFunc = (_, _, _, _) => Task.FromResult(new AgentResponse([
                new ChatMessage(ChatRole.Assistant, [childApprovalRequest])
            ]))
        };

        var function = childAgent.AsAIFunction(session: childSession);
        var context = new FunctionInvocationContext
        {
            CallContent = parentFunctionCall,
        };

        SetFunctionInvokingChatClientCurrentContext(context);

        try
        {
            // Act
            var result = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });
            var propagatedApprovals = RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);

            // Assert
            Assert.Equal(string.Empty, result?.ToString());
            Assert.True(context.Terminate);
            Assert.NotNull(propagatedApprovals);

            var propagatedApproval = Assert.Single(propagatedApprovals);
            Assert.Equal("approval-1", propagatedApproval.RequestId);
            Assert.Same(parentFunctionCall, propagatedApproval.ToolCall);
        }
        finally
        {
            SetFunctionInvokingChatClientCurrentContext(null);
            RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task InvokeAsync_WhenParentApprovalResolved_ResumesChildAgentWithChildApprovalResponseAsync(bool approved)
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var childFunctionCall = new FunctionCallContent("child-call", "SensitiveTool");
        var childApprovalRequest = new ToolApprovalRequestContent("approval-1", childFunctionCall);
        var childSession = new TestAgentSession();
        var callCount = 0;
        List<ChatMessage>? resumedMessages = null;
        AgentSession? resumedSession = null;

        var childAgent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, _, _) =>
            {
                callCount++;
                if (callCount == 1)
                {
                    return Task.FromResult(new AgentResponse([
                        new ChatMessage(ChatRole.Assistant, [childApprovalRequest])
                    ]));
                }

                resumedMessages = messages.ToList();
                resumedSession = session;
                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "child finished")));
            }
        };

        var function = childAgent.AsAIFunction(session: childSession);
        SetFunctionInvokingChatClientCurrentContext(new FunctionInvocationContext { CallContent = parentFunctionCall });

        try
        {
            _ = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });
            _ = RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);

            var parentApprovalResponse = new ToolApprovalResponseContent("approval-1", approved, parentFunctionCall)
            {
                Reason = "operator decision"
            };
            SetFunctionInvokingChatClientCurrentContext(new FunctionInvocationContext
            {
                CallContent = parentFunctionCall,
                Messages = [new ChatMessage(ChatRole.User, [parentApprovalResponse])],
            });

            // Act
            var result = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });

            // Assert
            Assert.Equal("child finished", result?.ToString());
            Assert.Equal(2, callCount);
            Assert.Same(childSession, resumedSession);

            var childApprovalResponse = Assert.Single(resumedMessages!
                .SelectMany(message => message.Contents)
                .OfType<ToolApprovalResponseContent>());

            Assert.Equal("approval-1", childApprovalResponse.RequestId);
            Assert.Equal(approved, childApprovalResponse.Approved);
            Assert.Equal("operator decision", childApprovalResponse.Reason);
            Assert.Same(childFunctionCall, childApprovalResponse.ToolCall);
        }
        finally
        {
            SetFunctionInvokingChatClientCurrentContext(null);
            RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);
        }
    }

    [Fact]
    public async Task InvokeAsync_WhenNoParentFunctionContext_DoesNotPropagateApprovalAsync()
    {
        // Arrange
        var childFunctionCall = new FunctionCallContent("child-call", "SensitiveTool");
        var childApprovalRequest = new ToolApprovalRequestContent("approval-1", childFunctionCall);
        var childAgent = new TestAIAgent
        {
            RunAsyncFunc = (_, _, _, _) => Task.FromResult(new AgentResponse([
                new ChatMessage(ChatRole.Assistant, [childApprovalRequest])
            ]))
        };

        var function = childAgent.AsAIFunction();
        SetFunctionInvokingChatClientCurrentContext(null);

        // Act
        var result = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });

        // Assert
        Assert.Equal(string.Empty, result?.ToString());
    }

    [Fact]
    public async Task InvokeAsync_WhenChildAgentRequestsMultipleApprovals_ResumesWithAllChildApprovalResponsesAsync()
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var childFunctionCall1 = new FunctionCallContent("child-call-1", "SensitiveToolA");
        var childFunctionCall2 = new FunctionCallContent("child-call-2", "SensitiveToolB");
        var childApprovalRequest1 = new ToolApprovalRequestContent("approval-1", childFunctionCall1);
        var childApprovalRequest2 = new ToolApprovalRequestContent("approval-2", childFunctionCall2);
        var childSession = new TestAgentSession();
        var callCount = 0;
        List<ToolApprovalResponseContent>? resumedApprovalResponses = null;

        var childAgent = new TestAIAgent
        {
            RunAsyncFunc = (messages, _, _, _) =>
            {
                callCount++;
                if (callCount == 1)
                {
                    return Task.FromResult(new AgentResponse([
                        new ChatMessage(ChatRole.Assistant, [childApprovalRequest1, childApprovalRequest2])
                    ]));
                }

                resumedApprovalResponses = messages
                    .SelectMany(message => message.Contents)
                    .OfType<ToolApprovalResponseContent>()
                    .ToList();

                return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "child finished")));
            }
        };

        var function = childAgent.AsAIFunction(session: childSession);
        SetFunctionInvokingChatClientCurrentContext(new FunctionInvocationContext { CallContent = parentFunctionCall });

        try
        {
            _ = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });
            _ = RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);

            var parentApprovalResponse = new ToolApprovalResponseContent("approval-1", true, parentFunctionCall);
            SetFunctionInvokingChatClientCurrentContext(new FunctionInvocationContext
            {
                CallContent = parentFunctionCall,
                Messages = [new ChatMessage(ChatRole.User, [parentApprovalResponse])],
            });

            // Act
            _ = await function.InvokeAsync(new AIFunctionArguments { ["query"] = "do sensitive work" });

            // Assert
            Assert.NotNull(resumedApprovalResponses);
            Assert.Equal(2, resumedApprovalResponses.Count);
            Assert.All(resumedApprovalResponses, response => Assert.True(response.Approved));
            Assert.Contains(resumedApprovalResponses, response => response.RequestId == "approval-1" && ReferenceEquals(response.ToolCall, childFunctionCall1));
            Assert.Contains(resumedApprovalResponses, response => response.RequestId == "approval-2" && ReferenceEquals(response.ToolCall, childFunctionCall2));
        }
        finally
        {
            SetFunctionInvokingChatClientCurrentContext(null);
            RootToolApprovalRequestPropagator.TakeApprovals(parentFunctionCall);
        }
    }

    private static void SetFunctionInvokingChatClientCurrentContext(FunctionInvocationContext? context)
    {
        var currentContextField = typeof(FunctionInvokingChatClient).GetField(
            "_currentContext",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);

        if (currentContextField?.GetValue(null) is AsyncLocal<FunctionInvocationContext?> asyncLocal)
        {
            asyncLocal.Value = context;
        }
    }

    private sealed class TestAgentSession : AgentSession;
}
