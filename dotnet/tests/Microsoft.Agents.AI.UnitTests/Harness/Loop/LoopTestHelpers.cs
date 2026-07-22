// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Shared helpers used by the LoopAgent and LoopEvaluator unit tests.
/// </summary>
internal static class LoopTestHelpers
{
    /// <summary>
    /// Creates a <see cref="DelegateLoopEvaluator"/> that re-invokes the agent (without feedback) while the
    /// supplied predicate returns <see langword="true"/>.
    /// </summary>
    public static DelegateLoopEvaluator While(Func<LoopContext, bool> shouldReinvoke) =>
        new((context, _) =>
            new ValueTask<LoopEvaluation>(
                shouldReinvoke(context) ? LoopEvaluation.Continue() : LoopEvaluation.Stop()));

    /// <summary>
    /// Creates a mocked judge <see cref="IChatClient"/> that always returns the supplied response text.
    /// </summary>
    public static IChatClient CreateJudgeClient(string responseText)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText)));
        return mock.Object;
    }

    /// <summary>
    /// Creates a mocked judge <see cref="IChatClient"/> that always returns the supplied response text and captures the
    /// messages it was invoked with via <paramref name="capturedMessages"/>.
    /// </summary>
    public static IChatClient CreateCapturingJudgeClient(string responseText, out List<ChatMessage> capturedMessages)
    {
        var captured = new List<ChatMessage>();
        capturedMessages = captured;
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((messages, _, _) =>
            {
                captured.Clear();
                captured.AddRange(messages);
            })
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText)));
        return mock.Object;
    }

    public static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(
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
}

/// <summary>
/// Captures the messages sent to a mocked non-streaming inner agent and produces responses by call index.
/// </summary>
internal sealed class InnerAgentCapture
{
    public InnerAgentCapture(Func<int, AgentResponse> responseFactory)
    {
        this.Mock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, session, _, _) =>
            {
                this.CallCount++;
                this.MessagesPerCall.Add(msgs.ToList());
                this.SessionsPerCall.Add(session);
            })
            .ReturnsAsync(() => responseFactory(this.CallCount));
    }

    public Mock<AIAgent> Mock { get; } = new();

    public AIAgent Agent => this.Mock.Object;

    public int CallCount { get; private set; }

    public List<List<ChatMessage>> MessagesPerCall { get; } = [];

    public List<AgentSession?> SessionsPerCall { get; } = [];
}

/// <summary>
/// Captures the messages sent to a mocked streaming inner agent and produces updates by call index.
/// </summary>
internal sealed class InnerStreamingCapture
{
    public InnerStreamingCapture(Func<int, AgentResponseUpdate[]> updatesFactory)
    {
        this.Mock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>((msgs, _, _, ct) =>
            {
                this.CallCount++;
                this.MessagesPerCall.Add(msgs.ToList());
                return LoopTestHelpers.ToAsyncEnumerableAsync(updatesFactory(this.CallCount), ct);
            });
    }

    public Mock<AIAgent> Mock { get; } = new();

    public AIAgent Agent => this.Mock.Object;

    public int CallCount { get; private set; }

    public List<List<ChatMessage>> MessagesPerCall { get; } = [];
}
