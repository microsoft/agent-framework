// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 6 — timeout-then-resume promotion. When the foreground attempt exceeds
/// <c>MaxWait</c>, the provider stores a rehydration token on the <see cref="DocumentEntry"/>;
/// the next <c>InvokingAsync</c> call replays it via the resume path and promotes the entry
/// in place. Tests substitute the foreground call via <c>AnalyzeOverride</c> and the resume
/// call via <c>ResumeOverride</c>; no test in this file hits the network.
/// </summary>
public sealed class ContextProviderPhase6Tests
{
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    public async Task InvokingAsync_TimeoutThenResume_PromotesOnNextTurn()
    {
        AnalysisResult readyResult = SharedTestFixtures.MakeInvoiceResult();
        AnalysisOutcome timeoutOutcome = new(
            Completed: false,
            Result: null,
            OperationId: "op-123",
            Error: null,
            Duration: TimeSpan.FromMilliseconds(10))
        {
            RehydrationTokenJson = "rt-json-stub",
        };

        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        FakeResumer resumer = new FakeResumer().Returns(
            "op-123",
            new AnalysisOutcome(
                Completed: true,
                Result: readyResult,
                OperationId: "op-123",
                Error: null,
                Duration: TimeSpan.FromMilliseconds(200)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer);

        AgentSessionFake session = new();
        TestAIAgentStub agent = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Turn 1 — attempt times out. Document tracked as Analyzing with a rehydration token.
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
        Assert.Equal(0, resumer.CallCount);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Equal(DocumentStatus.Analyzing, state.Documents["invoice.pdf"].Status);
        Assert.Equal("op-123", state.Documents["invoice.pdf"].OperationId);
        Assert.Equal("rt-json-stub", state.Documents["invoice.pdf"].RehydrationTokenJson);
        Assert.Empty(state.InjectedKeys);

        // Turn 2 — user asks something else, no new attachment. Provider should resume the
        // pending LRO via ResumeOverride, promote the doc, then inject it.
        ChatMessage turn2User = new(ChatRole.User, [new TextContent("Now summarize it.")]);
        AIContext turn2 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                agent,
                session,
                new AIContext { Messages = new List<ChatMessage> { turn2User } }),
            CancellationToken.None);

        Assert.Equal(1, resumer.CallCount);
        Assert.Equal(DocumentStatus.Ready, state.Documents["invoice.pdf"].Status);
        Assert.NotNull(state.Documents["invoice.pdf"].Result);
        Assert.Null(state.Documents["invoice.pdf"].RehydrationTokenJson);

        List<ChatMessage> turn2Messages = turn2.Messages!.ToList();
        Assert.Equal(2, turn2Messages.Count);
        Assert.Equal(ChatRole.System, turn2Messages[1].Role);
        string injectedText = string.Concat(turn2Messages[1].Contents.OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("CONTOSO LTD.", injectedText, StringComparison.Ordinal);

        Assert.Contains("invoice.pdf", state.InjectedKeys);
        // Foreground analyzer was only called turn 1.
        Assert.Equal(1, analyzer.CallCount);
    }

    [Fact]
    public async Task InvokingAsync_PromotedDocument_NotReinjectedOnSubsequentTurn()
    {
        AnalysisResult readyResult = SharedTestFixtures.MakeInvoiceResult();
        AnalysisOutcome timeoutOutcome = new(
            Completed: false,
            Result: null,
            OperationId: "op-1",
            Error: null,
            Duration: TimeSpan.FromMilliseconds(5))
        {
            RehydrationTokenJson = "rt-json-stub",
        };

        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        FakeResumer resumer = new FakeResumer().Returns(
            "op-1",
            new AnalysisOutcome(true, readyResult, "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer);

        AgentSessionFake session = new();
        TestAIAgentStub agent = new();

        // Turn 1 — drive the analyzing path.
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(agent, session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Turn 2 — resume completes, injection happens once.
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
    public async Task InvokingAsync_ResumeFails_StoresErrorAndDropsToken()
    {
        InvalidOperationException expected = new("simulated server failure");
        AnalysisOutcome timeoutOutcome = new(false, null, "op-fail", null, TimeSpan.FromMilliseconds(5))
        {
            RehydrationTokenJson = "rt-json-stub",
        };

        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        FakeResumer resumer = new FakeResumer().Returns(
            "op-fail",
            () => throw expected);

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer);

        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage user = new(ChatRole.User, [new TextContent("Read."), pdf]);

        // Turn 1 — timeout, entry stored as Analyzing.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { user } }),
            CancellationToken.None);

        // Turn 2 — resume throws; provider should mark the entry Failed without rethrowing.
        AIContext next = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Still?")]) } }),
            CancellationToken.None);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        DocumentEntry entry = state.Documents["invoice.pdf"];
        Assert.Equal(DocumentStatus.Failed, entry.Status);
        Assert.Equal("simulated server failure", entry.Error);
        Assert.Null(entry.RehydrationTokenJson);

        // Failed docs are NOT injected (only Ready docs are).
        List<ChatMessage> nextMessages = next.Messages!.ToList();
        Assert.Single(nextMessages);
        Assert.Equal(ChatRole.User, nextMessages[0].Role);
    }

    [Fact]
    public async Task DisposeAsync_WithPendingAnalyzingEntry_ReturnsPromptly()
    {
        // With the Plan-C rewrite there is no background runner to cancel. DisposeAsync
        // should simply return and leave the entry as Analyzing (the rehydration token can
        // be picked up by a future provider instance if it shares the same session state).
        AnalysisOutcome timeoutOutcome = new(false, null, "op-disposed", null, TimeSpan.FromMilliseconds(5))
        {
            RehydrationTokenJson = "rt-json-stub",
        };

        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer: null);

        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage user = new(ChatRole.User, [new TextContent("Read."), pdf]);

        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { user } }),
            CancellationToken.None);

        Stopwatch sw = Stopwatch.StartNew();
        await provider.DisposeAsync();
        sw.Stop();
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(2),
            $"DisposeAsync took {sw.Elapsed} — expected near-instant return.");

        // Status untouched.
        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Equal(DocumentStatus.Analyzing, state.Documents["invoice.pdf"].Status);
        Assert.Equal("rt-json-stub", state.Documents["invoice.pdf"].RehydrationTokenJson);
    }

    private static ContentUnderstandingContextProvider CreateProvider(
        FakeAnalyzer analyzer,
        FakeResumer? resumer = null) =>
        new(SharedTestFixtures.TestEndpoint, new FakeTokenCredential())
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
            ResumeOverride = resumer is null ? null : resumer.ResumeAsync,
        };
}
