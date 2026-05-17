// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 11 — provider-level parity gaps not previously covered:
/// URL input, multi-file analysis, same-turn duplicate filename, supported-media-types,
/// session isolation, and multi-file FileSearch upload.
/// </summary>
public sealed class ParityGapTests
{
    private static readonly Uri TestEndpoint = SharedTestFixtures.TestEndpoint;
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    // parity: python tests/cu/test_context_provider.py::TestBeforeRunNewFile::test_url_input_analyzed
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

    // parity: python tests/cu/test_context_provider.py::TestBeforeRunMultiFile::test_two_files_both_analyzed
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

    // parity: python tests/cu/test_context_provider.py::TestDuplicateDocumentKey::test_duplicate_in_same_turn_rejected
    [Fact]
    public async Task InvokingAsync_DuplicateFilenameInSameTurn_Throws()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        DataContent first = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        DataContent second = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage userMessage = new(ChatRole.User, [new TextContent("Two attachments same name"), first, second]);

        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            provider.InvokingAsync(
                new AIContextProvider.InvokingContext(
                    new TestAIAgentStub(), new AgentSessionFake(),
                    new AIContext { Messages = new List<ChatMessage> { userMessage } }),
                CancellationToken.None).AsTask());

        Assert.Contains("invoice.pdf", ex.Message, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestSupportedMediaTypes::test_pdf_supported
    // parity: python tests/cu/test_context_provider.py::TestSupportedMediaTypes::test_audio_supported
    // parity: python tests/cu/test_context_provider.py::TestSupportedMediaTypes::test_video_supported
    // parity: python tests/cu/test_context_provider.py::TestSupportedMediaTypes::test_zip_not_supported
    [Theory]
    [InlineData("application/pdf", true)]
    [InlineData("image/png", true)]
    [InlineData("image/jpeg", true)]
    [InlineData("audio/mpeg", true)]
    [InlineData("audio/wav", true)]
    [InlineData("video/mp4", true)]
    [InlineData("application/zip", false)]
    [InlineData("text/plain", false)]
    [InlineData("application/json", false)]
    public void SupportedMediaTypes_MatchesPythonAllowList(string mediaType, bool expectedSupported)
    {
        DataContent dc = new(new byte[] { 0x00 }, mediaType) { Name = "sample.bin" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        bool detected = AttachmentDetector.Detect([msg]).Any();
        Assert.Equal(expectedSupported, detected);
    }

    // parity: python tests/cu/test_context_provider.py::TestSessionIsolation::test_background_task_isolated_per_session
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

    // parity: python tests/cu/test_context_provider.py::TestSessionIsolation::test_completed_task_resolves_in_correct_session
    [Fact]
    public async Task BackgroundCompletion_ResolvesAgainstTheOriginatingSessionOnly()
    {
        AnalysisResult ready = SharedTestFixtures.MakeInvoiceResult();
        TaskCompletionSource<AnalysisOutcome> gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
        AnalysisAttempt timeoutAttempt = new(
            Outcome: new AnalysisOutcome(false, null, "op-1", null, TimeSpan.FromMilliseconds(5)),
            Continuation: _ => gate.Task);

        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", timeoutAttempt);

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake sessionA = new();
        AgentSessionFake sessionB = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Session A starts the analysis; it times out and goes to background.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), sessionA,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Unblock the background runner — promotion happens in session A's registry.
        gate.SetResult(new AnalysisOutcome(true, ready, "op-1", null, TimeSpan.FromMilliseconds(80)));
        await provider.WaitForBackgroundTasksAsync();

        ContentUnderstandingProviderState stateA = provider.GetStateForTesting(sessionA);
        ContentUnderstandingProviderState stateB = provider.GetStateForTesting(sessionB);

        Assert.Equal(DocumentStatus.Ready, stateA.Documents["invoice.pdf"].Status);
        Assert.False(stateB.Documents.ContainsKey("invoice.pdf"));
    }

    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_file_search_multiple_files
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
            TestEndpoint, new FakeTokenCredential(),
            opt =>
            {
                opt.FileSearchConfig = new FileSearchConfig
                {
                    Backend = backend,
                    VectorStoreId = "vs-xyz",
                    FileSearchTool = fileSearchTool,
                };
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

    private static ContentUnderstandingContextProvider CreateProvider(FakeAnalyzer analyzer) =>
        new(TestEndpoint, new FakeTokenCredential())
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };
}
