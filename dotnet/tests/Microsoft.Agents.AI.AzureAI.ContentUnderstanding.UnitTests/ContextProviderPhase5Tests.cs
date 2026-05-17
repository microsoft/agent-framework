// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 5 — single-document happy path: detect → analyze → render → rebuild messages
/// (Strategy C) → inject system note. All tests substitute the analyze pipeline via
/// <c>AnalyzeOverride</c>; no test in this file hits the network.
/// </summary>
public sealed class ContextProviderPhase5Tests
{
    private static readonly Uri TestEndpoint = SharedTestFixtures.TestEndpoint;

    private static readonly byte[] s_pdfBytes = SharedTestFixtures.LoadFixturePdf();

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunNewFile::test_single_pdf_analyzed
    // parity: python tests/cu/test_context_provider.py::TestBinaryStripping::test_supported_files_stripped
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_no_file_search_injects_content
    public async Task InvokingAsync_StripsAttachment_AndInjectsRenderedDocument()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(
                Completed: true,
                Result: MakeInvoiceResult(),
                OperationId: "op-1",
                Error: null,
                Duration: TimeSpan.FromMilliseconds(42)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        AgentSessionFake session = new();
        DataContent pdfAttachment = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage userMessage = new(ChatRole.User,
            [new TextContent("Summarize this invoice."), pdfAttachment]);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                session,
                new AIContext { Messages = new List<ChatMessage> { userMessage } }),
            CancellationToken.None);

        Assert.Equal(1, analyzer.CallCount);
        Assert.Equal(("invoice.pdf", AnalyzerSelector.DocumentAnalyzer), analyzer.Calls[0]);

        List<ChatMessage> messages = result.Messages!.ToList();
        // Original user message preserved (minus the DataContent) + injected system note.
        Assert.Equal(2, messages.Count);

        ChatMessage rebuiltUser = messages[0];
        Assert.Equal(ChatRole.User, rebuiltUser.Role);
        Assert.DoesNotContain(rebuiltUser.Contents, c => c is DataContent);
        Assert.Single(rebuiltUser.Contents);
        Assert.Equal("Summarize this invoice.", ((TextContent)rebuiltUser.Contents[0]).Text);

        ChatMessage systemNote = messages[1];
        Assert.Equal(ChatRole.System, systemNote.Role);
        Assert.True(systemNote.Contents.Count >= 2);
        Assert.IsType<TextContent>(systemNote.Contents[0]);
        Assert.Contains("pre-analyzed", ((TextContent)systemNote.Contents[0]).Text, StringComparison.OrdinalIgnoreCase);
        Assert.IsType<TextContent>(systemNote.Contents[1]);
        Assert.Contains("CONTOSO LTD.", ((TextContent)systemNote.Contents[1]).Text, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestDuplicateDocumentKey::test_duplicate_filename_rejected
    public async Task InvokingAsync_DuplicateFilenameInSameSession_Throws()
    {
        AnalysisOutcome success = new(true, MakeInvoiceResult(), "op-1", null, TimeSpan.Zero);
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns("invoice.pdf", success);

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        AgentSessionFake session = new();

        // First turn → registers invoice.pdf in state.
        DataContent first = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        _ = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), session,
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [first]) } }),
            CancellationToken.None);

        // Second turn → same filename → must throw.
        DataContent second = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            provider.InvokingAsync(
                new AIContextProvider.InvokingContext(
                    new TestAIAgentStub(), session,
                    new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [second]) } }),
                CancellationToken.None).AsTask());

        Assert.Contains("invoice.pdf", ex.Message, StringComparison.Ordinal);
        // The fake analyzer was only invoked once (the second call must short-circuit before analysis).
        Assert.Equal(1, analyzer.CallCount);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestBeforeRunNewFile::test_text_only_skipped
    // parity: python tests/cu/test_context_provider.py::TestBinaryStripping::test_unsupported_files_left_in_place
    public async Task InvokingAsync_UnsupportedMediaType_PassesThroughUntouched()
    {
        FakeAnalyzer analyzer = new();
        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        // text/plain is not in the supported set — must pass through.
        DataContent unsupported = new(new byte[] { 0x68, 0x69 }, "text/plain") { Name = "note.txt" };
        ChatMessage userMessage = new(ChatRole.User, [new TextContent("Read this."), unsupported]);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(),
                new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { userMessage } }),
            CancellationToken.None);

        Assert.Equal(0, analyzer.CallCount);
        List<ChatMessage> messages = result.Messages!.ToList();
        // No system note added; original message reached the LLM unchanged.
        Assert.Single(messages);
        Assert.Same(userMessage, messages[0]);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestErrorHandling::test_lazy_initialization_on_before_run
    public async Task EnsureClientAsync_LazyInit_IsIdempotentUnderConcurrentLoad()
    {
        CountingClientFactory factory = new();
        ContentUnderstandingContextProvider provider = new(TestEndpoint, new FakeTokenCredential())
        {
            ClientFactoryOverride = factory,
        };

        await using (provider)
        {
            Assert.Equal(0, factory.CallCount); // Ctor never hits the factory.

            Task<ContentUnderstandingClient>[] callers = Enumerable.Range(0, 16)
                .Select(_ => provider.EnsureClientForTestingAsync(CancellationToken.None).AsTask())
                .ToArray();

            ContentUnderstandingClient[] results = await Task.WhenAll(callers);

            Assert.Equal(1, factory.CallCount);
            Assert.All(results, c => Assert.Same(results[0], c));
        }
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestCloseCancel::test_close_cleans_up (idempotent close path)
    public async Task DisposeAsync_IsIdempotent_AfterInvokingPath()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(true, MakeInvoiceResult(), "op", null, TimeSpan.FromMilliseconds(1)));

        ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        _ = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, [pdf]) } }),
            CancellationToken.None);

        await provider.DisposeAsync();
        await provider.DisposeAsync(); // second call must not throw.
    }

    [Fact]
    // parity: N/A — .NET ObjectDisposedException contract; Python relies on duck typing.
    public async Task InvokingAsync_AfterDispose_Throws()
    {
        FakeAnalyzer analyzer = new();
        ContentUnderstandingContextProvider provider = CreateProvider(analyzer);
        await provider.DisposeAsync();

        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            provider.InvokingAsync(
                new AIContextProvider.InvokingContext(
                    new TestAIAgentStub(), new AgentSessionFake(),
                    new AIContext { Messages = new List<ChatMessage> { new(ChatRole.User, "hi") } }),
                CancellationToken.None).AsTask());
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestErrorHandling::test_cu_service_error
    public async Task InvokingAsync_AnalysisFailure_MarksFailed_StillStripsAttachment()
    {
        FakeAnalyzer analyzer = new FakeAnalyzer().Returns(
            "invoice.pdf",
            new AnalysisOutcome(
                Completed: false,
                Result: null,
                OperationId: null,
                Error: new InvalidOperationException("CU service rejected the request."),
                Duration: TimeSpan.FromMilliseconds(5)));

        await using ContentUnderstandingContextProvider provider = CreateProvider(analyzer);

        DataContent pdf = new(s_pdfBytes, "application/pdf") { Name = "invoice.pdf" };
        ChatMessage user = new(ChatRole.User, [new TextContent("Read."), pdf]);

        AIContext result = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(
                new TestAIAgentStub(), new AgentSessionFake(),
                new AIContext { Messages = new List<ChatMessage> { user } }),
            CancellationToken.None);

        List<ChatMessage> messages = result.Messages!.ToList();
        // No system note (no successful render); but the attachment is still stripped.
        Assert.Single(messages);
        Assert.DoesNotContain(messages[0].Contents, c => c is DataContent);
    }

    private static ContentUnderstandingContextProvider CreateProvider(FakeAnalyzer analyzer) =>
        new(TestEndpoint, new FakeTokenCredential())
        {
            // The lazy-init seam is exercised independently; analysis path here is fully mocked.
            ClientFactoryOverride = new CountingClientFactory(),
            AnalyzeOverride = analyzer.AnalyzeAsync,
        };

    private static AnalysisResult MakeInvoiceResult() => SharedTestFixtures.MakeInvoiceResult();
}
