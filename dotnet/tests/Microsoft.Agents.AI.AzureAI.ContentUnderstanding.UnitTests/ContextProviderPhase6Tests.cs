// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 6 — background continuation and cross-turn promotion. When the foreground attempt
/// exceeds <c>MaxWait</c>, the provider hands the LRO off to a background runner; subsequent
/// turns scan the registry and inject any newly-Ready document exactly once. Tests substitute
/// the analyze pipeline via <c>AnalyzeOverride</c>; no test in this file hits the network.
/// </summary>
public sealed class ContextProviderPhase6Tests
{
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunTimeout::test_exceeds_max_wait_defers_to_background
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunPendingResolution::test_pending_completes_on_next_turn
    public async Task InvokingAsync_TimeoutThenResume_PromotesOnNextTurn()
    {
        AnalysisResult readyResult = SharedTestFixtures.MakeInvoiceResult();
        TaskCompletionSource<AnalysisOutcome> continuationGate = new(TaskCreationOptions.RunContinuationsAsynchronously);

        AnalysisAttempt timeoutAttempt = new(
            Outcome: new AnalysisOutcome(
                Completed: false,
                Result: null,
                OperationId: "op-123",
                Error: null,
                Duration: TimeSpan.FromMilliseconds(10)),
            Continuation: _ => continuationGate.Task);

        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", timeoutAttempt);
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        TestAIAgentStub agent = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Turn 1 — attempt times out. Document tracked as Analyzing; binary stripped but no system note.
        ChatMessage turn1User = new(ChatRole.User, [new TextContent("Read this."), pdf]);
        AIContext turn1 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                agent,
                session,
                new AIContext { Messages = new List<ChatMessage> { turn1User } }),
            CancellationToken.None);

        List<ChatMessage> turn1Messages = turn1.Messages!.ToList();
        Assert.Single(turn1Messages);
        Assert.DoesNotContain(turn1Messages[0].Contents, c => c is DataContent);
        Assert.Equal(1, analyzer.CallCount);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Equal(DocumentStatus.Analyzing, state.Documents["invoice.pdf"].Status);
        Assert.Equal("op-123", state.Documents["invoice.pdf"].OperationId);
        Assert.Empty(state.InjectedKeys);

        // Unblock the background runner: completion arrives.
        continuationGate.SetResult(new AnalysisOutcome(
            Completed: true,
            Result: readyResult,
            OperationId: "op-123",
            Error: null,
            Duration: TimeSpan.FromMilliseconds(200)));
        await provider.WaitForBackgroundTasksAsync();

        // Runner should have promoted the doc in place.
        Assert.Equal(DocumentStatus.Ready, state.Documents["invoice.pdf"].Status);
        Assert.NotNull(state.Documents["invoice.pdf"].Result);

        // Turn 2 — user asks something else, no new attachment. Provider should inject the ready doc.
        ChatMessage turn2User = new(ChatRole.User, [new TextContent("Now summarize it.")]);
        AIContext turn2 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                agent,
                session,
                new AIContext { Messages = new List<ChatMessage> { turn2User } }),
            CancellationToken.None);

        List<ChatMessage> turn2Messages = turn2.Messages!.ToList();
        Assert.Equal(2, turn2Messages.Count);
        Assert.Equal(ChatRole.System, turn2Messages[1].Role);
        string injectedText = string.Concat(turn2Messages[1].Contents.OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("CONTOSO LTD.", injectedText, StringComparison.Ordinal);

        Assert.Contains("invoice.pdf", state.InjectedKeys);
        // Background runner ran exactly once; foreground analyzer was only called turn 1.
        Assert.Equal(1, analyzer.CallCount);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestSessionState::test_documents_persist_across_turns
    public async Task InvokingAsync_PromotedDocument_NotReinjectedOnSubsequentTurn()
    {
        AnalysisResult readyResult = SharedTestFixtures.MakeInvoiceResult();
        TaskCompletionSource<AnalysisOutcome> gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
        AnalysisAttempt timeoutAttempt = new(
            Outcome: new AnalysisOutcome(false, null, "op-1", null, TimeSpan.FromMilliseconds(5)),
            Continuation: _ => gate.Task);

        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", timeoutAttempt);
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        TestAIAgentStub agent = new();

        // Turn 1 — drive the analyzing path.
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(agent, session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        gate.SetResult(new AnalysisOutcome(true, readyResult, "op-1", null, TimeSpan.FromMilliseconds(50)));
        await provider.WaitForBackgroundTasksAsync();

        // Turn 2 — injection happens once.
        AIContext turn2 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(agent, session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Summary?")]) } }),
            CancellationToken.None);
        Assert.Equal(2, turn2.Messages!.ToList().Count);

        // Turn 3 — no re-injection. Only the user message survives.
        AIContext turn3 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(agent, session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Anything else?")]) } }),
            CancellationToken.None);
        List<ChatMessage> turn3Messages = turn3.Messages!.ToList();
        Assert.Single(turn3Messages);
        Assert.Equal(ChatRole.User, turn3Messages[0].Role);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunPendingFailure::test_pending_task_failure_updates_state
    public async Task InvokingAsync_BackgroundRunner_HandlesFailure_StoresError()
    {
        InvalidOperationException expected = new("simulated server failure");
        AnalysisAttempt failingAttempt = new(
            Outcome: new AnalysisOutcome(false, null, "op-fail", null, TimeSpan.FromMilliseconds(5)),
            Continuation: _ => Task.FromException<AnalysisOutcome>(expected));

        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", failingAttempt);
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage user = new(ChatRole.User, [new TextContent("Read."), pdf]);

        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { user } }),
            CancellationToken.None);

        // Runner promoted to Failed in place; awaiting it must not throw (runner swallows).
        await provider.WaitForBackgroundTasksAsync();

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        DocumentEntry entry = state.Documents["invoice.pdf"];
        Assert.Equal(DocumentStatus.Failed, entry.Status);
        Assert.Equal("simulated server failure", entry.Error);

        // Failed docs are NOT injected on the next turn (only Ready docs are).
        AIContext next = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Still?")]) } }),
            CancellationToken.None);
        List<ChatMessage> nextMessages = next.Messages!.ToList();
        Assert.Single(nextMessages);
        Assert.Equal(ChatRole.User, nextMessages[0].Role);
    }

    [Fact]
    // parity: N/A — .NET CancellationToken propagation invariant; Python uses asyncio.Task.cancel().
    public async Task DisposeAsync_CancelsInflightRunner_LeavesStatusAnalyzing()
    {
        // Continuation that never completes on its own, but honors the cancellation token from
        // the provider's _disposeCts. We use TaskCompletionSource + ct.Register so cancel propagates.
        TaskCompletionSource<AnalysisOutcome> tcs = new(TaskCreationOptions.RunContinuationsAsynchronously);

        AnalysisAttempt blockingAttempt = new(
            Outcome: new AnalysisOutcome(false, null, "op-disposed", null, TimeSpan.FromMilliseconds(5)),
            Continuation: ct =>
            {
                ct.Register(() => tcs.TrySetCanceled(ct));
                return tcs.Task;
            });

        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", blockingAttempt);
        ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage user = new(ChatRole.User, [new TextContent("Read."), pdf]);

        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { user } }),
            CancellationToken.None);

        // Dispose should cancel the runner and return well within the 2-second bound.
        Stopwatch sw = Stopwatch.StartNew();
        await provider.DisposeAsync();
        sw.Stop();
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(3),
            $"DisposeAsync took {sw.Elapsed} — runner cancellation did not propagate.");

        // Status untouched: runner saw OCE and left the entry as Analyzing.
        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Equal(DocumentStatus.Analyzing, state.Documents["invoice.pdf"].Status);
    }

    private static ContentUnderstandingContextProvider CreateProvider(FakeAnalyzer analyzer) =>
        new(SharedTestFixtures.TestEndpoint, new FakeTokenCredential())
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };
}
