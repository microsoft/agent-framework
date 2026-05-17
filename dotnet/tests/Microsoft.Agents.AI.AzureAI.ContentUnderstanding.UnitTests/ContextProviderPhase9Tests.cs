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
/// Phase 9 — <c>FileSearchConfig</c> wiring through <see cref="ContentUnderstandingContextProvider"/>.
/// Covers: vector-store uploads on ready, message-injection skip, tool/instructions surfacing,
/// empty-payload skip, failure path, cross-turn promotion, and disposal cleanup.
/// </summary>
public sealed class ContextProviderPhase9Tests
{
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_file_search_uploads_to_vector_store
    public async Task InvokingAsync_WithFileSearchConfig_UploadsAndSurfacesToolAndInstructions()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer,
            backend,
            fileSearchTool,
            vectorStoreId: "vs-abc",
            includeFields: false);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext
                {
                    Instructions = "You are helpful.",
                    Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) },
                }),
            CancellationToken.None);

        // Exactly one upload, with the expected vector store id and `.md` suffix.
        FakeFileSearchBackend.UploadCall upload = Assert.Single(backend.UploadCalls);
        Assert.Equal("vs-abc", upload.VectorStoreId);
        Assert.Equal("invoice.pdf.md", upload.Filename);
        Assert.Contains("CONTOSO LTD.", upload.Payload, StringComparison.Ordinal);
        // IncludeFields=false → no fields block in the uploaded payload.
        Assert.DoesNotContain("fields:", upload.Payload, StringComparison.Ordinal);

        // file_search tool was appended to AIContext.Tools.
        List<AITool> tools = result.Tools!.ToList();
        Assert.Contains(fileSearchTool, tools);
        // The two built-in CU tools are still there too.
        Assert.Contains(tools, t => t is AIFunction f && f.Name == "list_documents");
        Assert.Contains(tools, t => t is AIFunction f && f.Name == "get_analyzed_document");

        // Instructions extended with guidance.
        Assert.NotNull(result.Instructions);
        Assert.Contains("You are helpful.", result.Instructions, StringComparison.Ordinal);
        Assert.Contains("Tool usage guidelines", result.Instructions, StringComparison.Ordinal);
        Assert.Contains("file_search", result.Instructions, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_file_search_no_content_injection
    public async Task InvokingAsync_WithFileSearchConfig_DoesNotInjectFullDocumentBodyIntoMessages()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Every message + content combined.
        string combinedMessageText = string.Join(
            "\n",
            result.Messages!.SelectMany(m => m.Contents).OfType<TextContent>().Select(t => t.Text));

        // Short note must be present.
        Assert.Contains("invoice.pdf", combinedMessageText, StringComparison.Ordinal);
        Assert.Contains("indexed in vector store", combinedMessageText, StringComparison.Ordinal);

        // The full markdown body must NOT have been injected (vector store carries it instead).
        Assert.DoesNotContain("CONTOSO LTD.", combinedMessageText, StringComparison.Ordinal);
        Assert.DoesNotContain("# INVOICE", combinedMessageText, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_include_fields_opt_in (provider-side wiring)
    public async Task InvokingAsync_WithIncludeFieldsTrue_UploadPayloadContainsFieldsBlock()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool, includeFields: true);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        FakeFileSearchBackend.UploadCall upload = Assert.Single(backend.UploadCalls);
        Assert.Contains("fields:", upload.Payload, StringComparison.Ordinal);
        Assert.Contains("CONTOSO LTD.", upload.Payload, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_file_search_skips_empty_markdown
    public async Task InvokingAsync_EmptyRenderableBody_SkipsUploadAndEmitsNote()
    {
        // Make an AnalysisResult whose rendering has front-matter only (no body content).
        AnalysisResult emptyContent = ContentUnderstandingModelFactory.AnalysisResult(
            contents:
            [
                ContentUnderstandingModelFactory.DocumentContent(
                    mimeType: "application/pdf",
                    markdown: "   ",
                    fields: null,
                    startPageNumber: 1,
                    endPageNumber: 1),
            ]);

        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "blank.pdf",
            new AnalysisOutcome(true, emptyContent, "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool);
        AgentSessionFake session = new();

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "blank.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // No upload happened.
        Assert.Empty(backend.UploadCalls);

        // The entry remains Ready (this is not a failure path).
        ContentUnderstandingProviderState st = provider.GetStateForTesting(session);
        DocumentEntry entry = st.Documents["blank.pdf"];
        Assert.Equal(DocumentStatus.Ready, entry.Status);
        Assert.Null(entry.VectorStoreFileId);

        // A short skip note is emitted to the LLM.
        string combinedText = string.Join("\n",
            result.Messages!.SelectMany(m => m.Contents).OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("blank.pdf", combinedText, StringComparison.Ordinal);
        Assert.Contains("no searchable text", combinedText, StringComparison.Ordinal);
    }

    [Fact]
    // parity: N/A — .NET defensive: backend errors must surface to LLM; Python relies on natural exception propagation.
    public async Task InvokingAsync_BackendThrows_StatusBecomesFailedAndNoteEmitted()
    {
        FakeFileSearchBackend backend = new()
        {
            UploadHandler = (_, _) => throw new InvalidOperationException("simulated upload failure"),
        };
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool);
        AgentSessionFake session = new();

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Status moved to Failed.
        ContentUnderstandingProviderState st = provider.GetStateForTesting(session);
        DocumentEntry entry = st.Documents["invoice.pdf"];
        Assert.Equal(DocumentStatus.Failed, entry.Status);
        Assert.Equal("simulated upload failure", entry.Error);
        Assert.Null(entry.VectorStoreFileId);

        // Note mentions failure to LLM.
        string combinedText = string.Join("\n",
            result.Messages!.SelectMany(m => m.Contents).OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("failed to upload", combinedText, StringComparison.Ordinal);
        Assert.Contains("simulated upload failure", combinedText, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_cleanup_deletes_uploaded_files
    // parity: python tests/cu/test_context_provider.py::TestCloseCancel::test_close_cleans_up (cleanup half)
    public async Task DisposeAsync_DeletesEveryUploadedFile()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer()
            .Returns("invoice.pdf",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)))
            .Returns("invoice2.pdf",
                new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-2", null, TimeSpan.FromMilliseconds(50)));

        ContentUnderstandingContextProvider provider = CreateProvider(analyzer, backend, fileSearchTool);
        AgentSessionFake session = new();

        DataContent pdf1 = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        DataContent pdf2 = new(s_pdfBytes, "application/pdf") { Name = "invoice2.pdf" };

        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Two."), pdf1, pdf2]) } }),
            CancellationToken.None);

        Assert.Equal(2, backend.UploadCalls.Count);
        Assert.Empty(backend.DeleteCalls);

        await provider.DisposeAsync();

        // Each uploaded file id should have been requested for deletion exactly once.
        Assert.Equal(2, backend.DeleteCalls.Count);
        HashSet<string> deleted = new(backend.DeleteCalls, StringComparer.Ordinal);
        // Fake ids start at file-0001, file-0002 ...
        Assert.Contains("file-0001", deleted);
        Assert.Contains("file-0002", deleted);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_pending_resolution_uploads_to_vector_store
    public async Task InvokingAsync_BackgroundPromoted_UploadHappensOnNextTurn()
    {
        AnalysisResult readyResult = SharedTestFixtures.MakeInvoiceResult();
        TaskCompletionSource<AnalysisOutcome> gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
        AnalysisAttempt attempt = new(
            Outcome: new AnalysisOutcome(false, null, "op-1", null, TimeSpan.FromMilliseconds(5)),
            Continuation: _ => gate.Task);

        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().ReturnsAttempt("invoice.pdf", attempt);
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, backend, fileSearchTool);
        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Turn 1 — analysis times out, entry is Analyzing, NO upload yet.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);
        Assert.Empty(backend.UploadCalls);

        // Background completion → entry becomes Ready, SearchPayload populated.
        gate.SetResult(new AnalysisOutcome(true, readyResult, "op-1", null, TimeSpan.FromMilliseconds(100)));
        await provider.WaitForBackgroundTasksAsync();

        // Turn 2 — cross-turn promotion should now upload.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Anything?")]) } }),
            CancellationToken.None);

        FakeFileSearchBackend.UploadCall upload = Assert.Single(backend.UploadCalls);
        Assert.Equal("invoice.pdf.md", upload.Filename);
        Assert.Contains("CONTOSO LTD.", upload.Payload, StringComparison.Ordinal);

        ContentUnderstandingProviderState st = provider.GetStateForTesting(session);
        Assert.Equal("file-0001", st.Documents["invoice.pdf"].VectorStoreFileId);
    }

    private static ContentUnderstandingContextProvider CreateProvider(
        FakeAnalyzer analyzer,
        FakeFileSearchBackend backend,
        FakeAITool fileSearchTool,
        string vectorStoreId = "vs-abc",
        bool includeFields = false) =>
        new(SharedTestFixtures.TestEndpoint,
            new FakeTokenCredential(),
            opt =>
            {
                opt.FileSearchConfig = new FileSearchConfig
                {
                    Backend = backend,
                    VectorStoreId = vectorStoreId,
                    FileSearchTool = fileSearchTool,
                    IncludeFields = includeFields,
                };
            })
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };
}
