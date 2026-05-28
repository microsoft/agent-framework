// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 7 — auto-registered tools (<c>list_documents</c>, <c>get_analyzed_document</c>).
/// Verifies the provider's <c>AIContext.Tools</c> wiring plus tool behavior (live state,
/// section selection, unknown-name / still-analyzing error strings).
/// </summary>
public sealed class ContextProviderPhase7Tests
{
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    public async Task InvokingAsync_NoDocuments_DoesNotSurfaceTools()
    {
        FakeAnalyzer analyzer = new();
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Hello.")]) } }),
            CancellationToken.None);

        Assert.Null(result.Tools);
    }

    [Fact]
    public async Task InvokingAsync_WithReadyDocument_SurfacesBothTools()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        List<AITool> tools = result.Tools!.ToList();
        Assert.Equal(2, tools.Count);
        Assert.Contains(tools, t => t is AIFunction f && f.Name == "list_documents");
        Assert.Contains(tools, t => t is AIFunction f && f.Name == "get_analyzed_document");
    }

    [Fact]
    public async Task InvokingAsync_SameToolInstances_AcrossTurns()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        AgentSessionFake session = new();

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext turn1 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        AIContext turn2 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("More?")]) } }),
            CancellationToken.None);

        Dictionary<string, AIFunction> t1 = turn1.Tools!.OfType<AIFunction>().ToDictionary(f => f.Name, f => f);
        Dictionary<string, AIFunction> t2 = turn2.Tools!.OfType<AIFunction>().ToDictionary(f => f.Name, f => f);
        Assert.Same(t1["list_documents"], t2["list_documents"]);
        Assert.Same(t1["get_analyzed_document"], t2["get_analyzed_document"]);
    }

    [Fact]
    public async Task ListDocumentsTool_ReflectsPostPromotionState()
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
            new AnalysisOutcome(true, readyResult, "op-1", null, TimeSpan.FromMilliseconds(100)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer);
        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Turn 1 — document is Analyzing.
        AIContext turn1 = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);
        AIFunction list = turn1.Tools!.OfType<AIFunction>().First(f => f.Name == "list_documents");

        // Invoke the tool now — should see Analyzing.
        AIFunctionArguments noArgs = new();
        object? snapshot1 = await list.InvokeAsync(noArgs, CancellationToken.None);
        Assert.Contains("Analyzing", snapshot1!.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain("Ready", snapshot1!.ToString(), StringComparison.Ordinal);

        // Turn 2 — resume promotes the entry in place.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Done?")]) } }),
            CancellationToken.None);

        // Same AIFunction instance now sees Ready.
        object? snapshot2 = await list.InvokeAsync(noArgs, CancellationToken.None);
        Assert.Contains("Ready", snapshot2!.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetAnalyzedDocumentTool_Default_ReturnsFullRender_Markdown_StripsFields()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        AIFunction get = result.Tools!.OfType<AIFunction>().First(f => f.Name == "get_analyzed_document");

        AIFunctionArguments defaultArgs = new() { ["documentName"] = "invoice.pdf" };
        string defaultRendered = (await get.InvokeAsync(defaultArgs, CancellationToken.None))!.ToString()!;
        Assert.Contains("CONTOSO LTD.", defaultRendered, StringComparison.Ordinal);
        Assert.Contains("fields:", defaultRendered, StringComparison.Ordinal);

        AIFunctionArguments markdownArgs = new()
        {
            ["documentName"] = "invoice.pdf",
            ["section"] = AnalysisSection.Markdown,
        };
        string markdownOnly = (await get.InvokeAsync(markdownArgs, CancellationToken.None))!.ToString()!;
        Assert.Contains("CONTOSO LTD.", markdownOnly, StringComparison.Ordinal);
        Assert.DoesNotContain("fields:", markdownOnly, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetAnalyzedDocumentTool_UnknownDocument_ReturnsErrorString()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        AIFunction get = result.Tools!.OfType<AIFunction>().First(f => f.Name == "get_analyzed_document");
        AIFunctionArguments args = new() { ["documentName"] = "missing.pdf" };
        string response = (await get.InvokeAsync(args, CancellationToken.None))!.ToString()!;
        Assert.Equal("Document 'missing.pdf' not found", response);
    }

    [Fact]
    public async Task GetAnalyzedDocumentTool_StillAnalyzing_ReturnsStatusErrorString()
    {
        // Turn 1 records the entry as Analyzing with a token. With no ResumeOverride the
        // get_analyzed_document tool should still observe the Analyzing status before any
        // subsequent InvokingAsync triggers a resume attempt.
        AnalysisOutcome timeoutOutcome = new(false, null, "op-1", null, TimeSpan.FromMilliseconds(5))
        {
            RehydrationTokenJson = "rt-json-stub",
        };

        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        AIFunction get = result.Tools!.OfType<AIFunction>().First(f => f.Name == "get_analyzed_document");
        AIFunctionArguments args = new() { ["documentName"] = "invoice.pdf" };
        string response = (await get.InvokeAsync(args, CancellationToken.None))!.ToString()!;
        Assert.Equal("Document 'invoice.pdf' is still Analyzing", response);

        await provider.DisposeAsync();
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
