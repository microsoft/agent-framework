// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Text.Json;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.3 — internal state types are System.Text.Json round-trippable.
/// </summary>
public sealed class ProviderStateTests
{
    // parity: python tests/cu/test_models.py::TestDocumentEntry::test_construction
    [Fact]
    public void DocumentEntry_RoundTripsAllFields()
    {
        var entry = new DocumentEntry
        {
            DocumentKey = "invoice.pdf",
            Filename = "invoice.pdf",
            MediaType = "application/pdf",
            AnalyzerId = "prebuilt-invoice",
            Status = DocumentStatus.Ready,
            AnalyzedAt = new DateTimeOffset(2026, 5, 15, 10, 0, 0, TimeSpan.Zero),
            AnalysisDuration = TimeSpan.FromSeconds(3.5),
            UploadDuration = TimeSpan.FromMilliseconds(750),
            Result = "rendered markdown",
            SearchPayload = "rendered markdown (no fields)",
            Error = null,
            OperationId = "op-abc-123",
        };

        var json = JsonSerializer.Serialize(entry);
        var clone = JsonSerializer.Deserialize<DocumentEntry>(json);

        Assert.NotNull(clone);
        Assert.Equal(entry, clone);
    }

    // parity: python tests/cu/test_models.py::TestDocumentEntry::test_failed_entry (nullable fields shape)
    [Fact]
    public void DocumentEntry_PreservesNullableTimestampsAndOptionalFields()
    {
        var entry = new DocumentEntry
        {
            DocumentKey = "video.mp4",
            Filename = "video.mp4",
            MediaType = "video/mp4",
            AnalyzerId = "prebuilt-videoSearch",
            Status = DocumentStatus.Analyzing,
            AnalyzedAt = null,
            AnalysisDuration = null,
            UploadDuration = null,
            Result = null,
            SearchPayload = null,
            Error = null,
            OperationId = "lro-handle",
        };

        var json = JsonSerializer.Serialize(entry);
        var clone = JsonSerializer.Deserialize<DocumentEntry>(json);

        Assert.NotNull(clone);
        Assert.Null(clone!.AnalyzedAt);
        Assert.Null(clone.AnalysisDuration);
        Assert.Null(clone.UploadDuration);
        Assert.Null(clone.Result);
        Assert.Null(clone.SearchPayload);
        Assert.Null(clone.Error);
        Assert.Equal("lro-handle", clone.OperationId);
        Assert.Equal(DocumentStatus.Analyzing, clone.Status);
    }

    // parity: N/A — .NET state JSON serialization; Python state is a plain dict.
    [Fact]
    public void ProviderState_RoundTripsDocumentsDictionary()
    {
        var state = new ContentUnderstandingProviderState();
        state.Documents["a.pdf"] = new DocumentEntry { DocumentKey = "a.pdf", Filename = "a.pdf", MediaType = "application/pdf", AnalyzerId = "prebuilt-documentSearch", Status = DocumentStatus.Ready, Result = "A" };
        state.Documents["b.mp3"] = new DocumentEntry { DocumentKey = "b.mp3", Filename = "b.mp3", MediaType = "audio/mpeg", AnalyzerId = "prebuilt-audioSearch", Status = DocumentStatus.Failed, Error = "boom" };

        var json = JsonSerializer.Serialize(state);
        var clone = JsonSerializer.Deserialize<ContentUnderstandingProviderState>(json);

        Assert.NotNull(clone);
        Assert.Equal(2, clone!.Documents.Count);
        Assert.Equal("A", clone.Documents["a.pdf"].Result);
        Assert.Equal(DocumentStatus.Failed, clone.Documents["b.mp3"].Status);
        Assert.Equal("boom", clone.Documents["b.mp3"].Error);
    }

    // parity: N/A — .NET InjectedKeys serialization; Python uses an in-state set.
    [Fact]
    public void ProviderState_RoundTripsInjectedKeys()
    {
        var state = new ContentUnderstandingProviderState();
        state.InjectedKeys.Add("a.pdf");
        state.InjectedKeys.Add("b.mp3");

        var json = JsonSerializer.Serialize(state);
        var clone = JsonSerializer.Deserialize<ContentUnderstandingProviderState>(json);

        Assert.NotNull(clone);
        Assert.Equal(2, clone!.InjectedKeys.Count);
        Assert.Contains("a.pdf", clone.InjectedKeys);
        Assert.Contains("b.mp3", clone.InjectedKeys);
    }

    // parity: N/A — .NET concurrency invariant (registry must be lock-free for background runner).
    [Fact]
    public void ProviderState_DocumentsIsConcurrentDictionary()
    {
        var state = new ContentUnderstandingProviderState();
        Assert.IsType<ConcurrentDictionary<string, DocumentEntry>>(state.Documents);
    }
}
