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
/// Phase 9 — <c>FileSearchConfig</c> wiring through <see cref="ContentUnderstandingContextProvider"/>.
/// Covers: vector-store uploads on ready, message-injection skip, tool/instructions surfacing,
/// empty-payload skip, failure path, cross-turn promotion, and disposal cleanup.
/// </summary>
public sealed class ContextProviderPhase9Tests
{
    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
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
            outputSections: AnalysisSection.Markdown);

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
        // OutputSections=Markdown only → no fields block in the uploaded payload.
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
    public async Task InvokingAsync_FilenameWithMarkdownSpecialChars_SanitizedOnUploadAndInNote()
    {
        // Filenames containing CommonMark-significant characters (especially `_`) render as
        // italics in chat UIs whenever the model emits the name without wrapping it in
        // backticks. The provider must replace those characters with `-` BEFORE the name
        // surfaces in either the vector-store registration or the per-document System note,
        // so the model can never echo back a name that breaks rendering. Original Filename
        // is preserved for state keys.
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "mixed_financial_invoices.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(20)));

        AgentSessionFake session = new();
        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "mixed_financial_invoices.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Upload registers the sanitized name (no underscores).
        FakeFileSearchBackend.UploadCall upload = Assert.Single(backend.UploadCalls);
        Assert.Equal("mixed-financial-invoices.pdf.md", upload.Filename);

        // Injected System note uses the sanitized name as well — model can echo verbatim
        // without breaking the chat-UI markdown renderer.
        string combinedMessageText = string.Join(
            "\n",
            result.Messages!.SelectMany(m => m.Contents).OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("mixed-financial-invoices.pdf", combinedMessageText, StringComparison.Ordinal);
        Assert.DoesNotContain("mixed_financial_invoices.pdf", combinedMessageText, StringComparison.Ordinal);

        // State still keys on the original filename so cross-turn dedup keeps working.
        ContentUnderstandingProviderState st = provider.GetStateForTesting(session);
        Assert.True(st.Documents.ContainsKey("mixed_financial_invoices.pdf"));
        Assert.Equal("mixed_financial_invoices.pdf", st.Documents["mixed_financial_invoices.pdf"].Filename);
    }

    [Fact]
    public async Task InvokingAsync_WithOutputSectionsIncludingFields_UploadPayloadContainsFieldsBlock()
    {
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromMilliseconds(50)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(
            analyzer, backend, fileSearchTool, outputSections: AnalysisSection.Markdown | AnalysisSection.Fields);

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
    public async Task InvokingAsync_UploadBudgetExhausted_DefersUploadButKeepsReadyResult()
    {
        // Analysis consumes the entire MaxWait budget (Duration 1s >> MaxWait 10ms), leaving
        // zero foreground time for the vector-store upload. The upload must be DEFERRED, not
        // failed: the analyzed result stays intact and Ready so list_documents /
        // get_analyzed_document keep serving it, and the next turn's promotion scan retries the
        // upload (VectorStoreFileId is still null). Regression guard for the budget-exhaustion
        // path that previously discarded a valid analysis by marking it Failed.
        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, SharedTestFixtures.MakeInvoiceResult(), "op-1", null, TimeSpan.FromSeconds(1)));

        await using ContentUnderstandingContextProvider provider = new(
            new ContentUnderstandingContextProviderOptions(SharedTestFixtures.TestEndpoint, new FakeTokenCredential())
            {
                MaxWait = TimeSpan.FromMilliseconds(10),
                FileSearchConfig = new FileSearchConfig
                {
                    Backend = backend,
                    VectorStoreId = "vs-abc",
                    FileSearchTool = fileSearchTool,
                },
            })
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };
        AgentSessionFake session = new();

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);

        // Upload was deferred, never attempted.
        Assert.Empty(backend.UploadCalls);

        // The analyzed result is preserved and still Ready (NOT marked Failed / cleared).
        ContentUnderstandingProviderState st = provider.GetStateForTesting(session);
        DocumentEntry entry = st.Documents["invoice.pdf"];
        Assert.Equal(DocumentStatus.Ready, entry.Status);
        Assert.Null(entry.VectorStoreFileId);   // upload pending → next turn retries.
        Assert.NotNull(entry.Result);           // rendered content intact.
        Assert.Contains("deferred", entry.Error!, StringComparison.OrdinalIgnoreCase);

        // The LLM note explains the deferral rather than reporting an upload failure.
        string combinedText = string.Join("\n",
            result.Messages!.SelectMany(m => m.Contents).OfType<TextContent>().Select(t => t.Text));
        Assert.Contains("deferred", combinedText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("failed to upload", combinedText, StringComparison.Ordinal);
    }

    [Fact]
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
    public async Task InvokingAsync_BackgroundPromoted_UploadHappensOnNextTurn()
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

        FakeFileSearchBackend backend = new();
        FakeAITool fileSearchTool = new();
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", timeoutOutcome);
        FakeResumer resumer = new FakeResumer().Returns(
            "op-1",
            new AnalysisOutcome(true, readyResult, "op-1", null, TimeSpan.FromMilliseconds(100)));
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer, backend, fileSearchTool, resumer: resumer);
        AgentSessionFake session = new();
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };

        // Turn 1 — analysis times out, entry is Analyzing, NO upload yet.
        await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [new TextContent("Read."), pdf]) } }),
            CancellationToken.None);
        Assert.Empty(backend.UploadCalls);

        // Turn 2 — resume completes mid-turn → entry becomes Ready → cross-turn promotion uploads.
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
        AnalysisSection outputSections = AnalysisSection.Default,
        FakeResumer? resumer = null) =>
        new(new ContentUnderstandingContextProviderOptions(SharedTestFixtures.TestEndpoint, new FakeTokenCredential())
        {
            OutputSections = outputSections,
            FileSearchConfig = new FileSearchConfig
            {
                Backend = backend,
                VectorStoreId = vectorStoreId,
                FileSearchTool = fileSearchTool,
            },
        })
        {
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
            ResumeOverride = resumer is null ? null : resumer.ResumeAsync,
        };
}
