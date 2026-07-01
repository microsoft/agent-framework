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
/// Phase 11 — provider-level coverage gaps:
/// URL input, multi-file analysis, same-turn duplicate filename, supported-media-types,
/// session isolation, and multi-file FileSearch upload.
/// </summary>
public sealed class CoverageGapTests
{
    private static readonly Uri s_testEndpoint = SharedTestFixtures.TestEndpoint;
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    public async Task InvokingAsync_UrlInput_AnalyzedAndInjected()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "report.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        UriContent pdfUrl = new("https://example.com/report.pdf", "application/pdf");
        ChatMessage userMessage = new(ChatRole.User, [new TextContent("Analyze this document"), pdfUrl]);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                session,
                new AIContext { Messages = new List<ChatMessage> { userMessage } }),
            CancellationToken.None);

        Assert.Equal(1, analyzer.CallCount);
        Assert.Equal("report.pdf", analyzer.Calls[0].Filename);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.True(state.Documents.ContainsKey("report.pdf"));
        Assert.Equal(DocumentStatus.Ready, state.Documents["report.pdf"].Status);

        List<ChatMessage> messages = result.Messages!.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.System, messages[1].Role);
    }

    [Fact]
    public async Task InvokingAsync_TwoAttachmentsInSameTurn_BothAnalyzed()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer()
            .Returns("doc1.pdf",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)))
            .Returns("chart.png",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-2", null, TimeSpan.FromMilliseconds(20)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "doc1.pdf" };
        DataContent png = new(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A }, "image/png") { Name = "chart.png" };
        ChatMessage userMessage = new(ChatRole.User,
            [new TextContent("Compare these documents"), pdf, png]);

        _ = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { userMessage } }),
            CancellationToken.None);

        Assert.Equal(2, analyzer.CallCount);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Equal(2, state.Documents.Count);
        Assert.Equal(DocumentStatus.Ready, state.Documents["doc1.pdf"].Status);
        Assert.Equal(DocumentStatus.Ready, state.Documents["chart.png"].Status);
    }

    [Fact]
    public async Task InvokingAsync_DuplicateFilenameInSameTurn_RejectedWithSystemNote()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        AgentSessionFake session = new();

        DataContent first = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        DataContent second = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage userMessage = new(ChatRole.User, [new TextContent("Two attachments same name"), first, second]);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { userMessage } }),
            CancellationToken.None);

        // First wins; analyzer invoked exactly once for the duplicate filename.
        Assert.Equal(1, analyzer.CallCount);

        ContentUnderstandingProviderState state = provider.GetStateForTesting(session);
        Assert.Single(state.Documents);
        Assert.Equal(DocumentStatus.Ready, state.Documents["invoice.pdf"].Status);

        List<ChatMessage> messages = result.Messages!.ToList();
        Assert.DoesNotContain(messages.SelectMany(m => m.Contents), c => c is DataContent);
        // A System note carrying the rejection text is emitted.
        Assert.Contains(messages, m =>
            m.Role == ChatRole.System
            && m.Contents.OfType<TextContent>().Any(t =>
                t.Text.Contains("already uploaded", StringComparison.Ordinal)
                && t.Text.Contains("rename", StringComparison.Ordinal)));
    }

    [Theory]
    [InlineData("application/pdf", true)]
    [InlineData("image/png", true)]
    [InlineData("image/jpeg", true)]
    [InlineData("audio/mpeg", true)]
    [InlineData("audio/wav", true)]
    [InlineData("video/mp4", true)]
    [InlineData("text/plain", true)]
    [InlineData("application/zip", false)]
    [InlineData("application/json", false)]
    public void SupportedMediaTypes_MatchesAllowList(string mediaType, bool expectedSupported)
    {
        DataContent dc = new(new byte[] { 0x00 }, mediaType) { Name = "sample.bin" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        bool detected = AttachmentDetector.Detect([msg]).Any();
        Assert.Equal(expectedSupported, detected);
    }

    [Fact]
    public async Task InvokingAsync_TwoSessions_HaveIsolatedRegistries()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake sessionA = new();
        AgentSessionFake sessionB = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Session A registers a document.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionA,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Session B starts cold; its state must not see session A's document.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionB,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Hello.")]) } }),
            CancellationToken.None);

        ContentUnderstandingProviderState stateA = provider.GetStateForTesting(sessionA);
        ContentUnderstandingProviderState stateB = provider.GetStateForTesting(sessionB);

        Assert.True(stateA.Documents.ContainsKey("invoice.pdf"));
        Assert.False(stateB.Documents.ContainsKey("invoice.pdf"));
    }

    [Fact]
    public async Task BackgroundCompletion_ResolvesAgainstTheOriginatingSessionOnly()
    {
        AnalysisResult ready = SharedTestFixtures.MakeInvoiceResult();
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
            new AnalysisOutcome(true, ready, "op-1", null, TimeSpan.FromMilliseconds(80)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, resumer);

        AgentSessionFake sessionA = new();
        AgentSessionFake sessionB = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Session A starts the analysis; it times out, entry stored under sessionA only.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionA,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        ContentUnderstandingProviderState stateAfterTurn1 = provider.GetStateForTesting(sessionA);
        Assert.Equal(DocumentStatus.Analyzing, stateAfterTurn1.Documents["invoice.pdf"].Status);

        // Session A turn 2: resume completes → entry promoted to Ready under sessionA.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionA,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Done?")]) } }),
            CancellationToken.None);

        // Session B never sees the document, even after sessionA promoted it.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionB,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Hello.")]) } }),
            CancellationToken.None);

        ContentUnderstandingProviderState stateA = provider.GetStateForTesting(sessionA);
        ContentUnderstandingProviderState stateB = provider.GetStateForTesting(sessionB);

        Assert.Equal(DocumentStatus.Ready, stateA.Documents["invoice.pdf"].Status);
        Assert.False(stateB.Documents.ContainsKey("invoice.pdf"));
        Assert.Equal(1, resumer.CallCount);
    }

    [Fact]
    public async Task InvokingAsync_FileSearch_MultipleAttachments_UploadEach()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer()
            .Returns("a.pdf",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)))
            .Returns("b.pdf",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-2", null, TimeSpan.FromMilliseconds(20)));

        await using ContentUnderstandingContextProvider provider = new(
            new ContentUnderstandingContextProviderOptions(s_testEndpoint, new FakeTokenCredential())
            {
                FileSearchConfig = new FileSearchConfig
                {
                    Backend = backend,
                    VectorStoreId = "vs-xyz",
                    FileSearchTool = fileSearchTool,
                },
            })
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };

        DataContent a = new(s_pdfBytes, "application/pdf") { Name = "a.pdf" };
        DataContent b = new(s_pdfBytes, "application/pdf") { Name = "b.pdf" };

        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Two."), a, b]) } }),
            CancellationToken.None);

        Assert.Equal(2, backend.UploadCalls.Count);
        HashSet<string> uploadedNames = new(backend.UploadCalls.Select(c => c.Filename), StringComparer.Ordinal);
        Assert.Contains("a.pdf.md", uploadedNames);
        Assert.Contains("b.pdf.md", uploadedNames);
    }

    private static ContentUnderstandingContextProvider CreateProvider(
        FakeAnalyzer analyzer,
        FakeResumer? resumer = null) =>
        new(s_testEndpoint, new FakeTokenCredential())
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
            ResumeOverride = resumer is null ? null : resumer.ResumeAsync,
        };
}
