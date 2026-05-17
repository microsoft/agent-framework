// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 11 — renderer-level parity gaps not previously covered:
/// classifier-category presence/absence, source-metadata propagation, field-value extraction,
/// and the "no rai_warnings when none present" negative.
/// </summary>
public sealed class RendererParityGapTests
{
    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_source_metadata_uses_filename
    [Fact]
    public void Render_UsesProvidedFilename_InSourceFrontMatter()
    {
        AnalysisResult result = SharedTestFixtures.MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "custom_name.pdf", AnalysisSection.Default);

        Assert.Contains("source: custom_name.pdf", rendered, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_field_values_extracted
    [Fact]
    public void Render_WithFields_EmitsFieldValuesIntoLlmInput()
    {
        AnalysisResult result = SharedTestFixtures.MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Default);

        Assert.Contains("fields:", rendered, StringComparison.Ordinal);
        Assert.Contains("VendorName", rendered, StringComparison.Ordinal);
        Assert.Contains("CONTOSO LTD.", rendered, StringComparison.Ordinal);
        Assert.Contains("TotalDue", rendered, StringComparison.Ordinal);
        Assert.Contains("$610.00", rendered, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestWarningsExtraction::test_warnings_omitted_when_empty
    [Fact]
    public void Render_NoWarnings_OmitsRaiWarningsKey()
    {
        AnalysisResult result = SharedTestFixtures.MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Default);

        Assert.DoesNotContain("rai_warnings", rendered, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestCategoryExtraction::test_category_omitted_when_none
    [Fact]
    public void Render_NoCategory_OmitsCategoryFrontMatterKey()
    {
        AnalysisResult result = SharedTestFixtures.MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Default);

        Assert.DoesNotContain("category:", rendered, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestCategoryExtraction::test_category_included_single_segment
    [Fact]
    public void Render_DocumentWithCategory_EmitsCategoryFrontMatterKey()
    {
        DocumentContent content = ContentUnderstandingModelFactory.DocumentContent(
            mimeType: "application/pdf",
            analyzerId: null,
            category: "Legal Contract",
            path: null,
            markdown: "Contract body text here.",
            fields: null,
            startPageNumber: 1,
            endPageNumber: 1);
        AnalysisResult result = ContentUnderstandingModelFactory.AnalysisResult(contents: [content]);

        string rendered = AnalysisRenderer.Render(result, "contract.pdf", AnalysisSection.Markdown);

        Assert.Contains("category:", rendered, StringComparison.Ordinal);
        Assert.Contains("Legal Contract", rendered, StringComparison.Ordinal);
    }

    // parity: python tests/cu/test_context_provider.py::TestCategoryExtraction::test_category_in_multi_segment_video
    // (per-segment category attribution: each block must carry its own category alongside its markdown body.)
    [Fact]
    public void Render_MultiSegmentVideo_AttachesPerSegmentCategoryToCorrectBlock()
    {
        AudioVisualContent seg1 = ContentUnderstandingModelFactory.AudioVisualContent(
            mimeType: "video/mp4",
            analyzerId: null,
            category: "ProductDemo",
            path: null,
            markdown: "Opening scene with product showcase.",
            fields: null,
            startTimeMsValue: 0,
            endTimeMsValue: 30_000);
        AudioVisualContent seg2 = ContentUnderstandingModelFactory.AudioVisualContent(
            mimeType: "video/mp4",
            analyzerId: null,
            category: "Testimonial",
            path: null,
            markdown: "Customer testimonial segment.",
            fields: null,
            startTimeMsValue: 30_000,
            endTimeMsValue: 60_000);
        AnalysisResult result = ContentUnderstandingModelFactory.AnalysisResult(contents: [seg1, seg2]);

        string rendered = AnalysisRenderer.Render(result, "promo.mp4", AnalysisSection.Markdown);

        string[] blocks = rendered.Split(["*****"], StringSplitOptions.None);
        Assert.Equal(2, blocks.Length);
        Assert.Contains("Opening scene with product showcase.", blocks[0], StringComparison.Ordinal);
        Assert.Contains("ProductDemo", blocks[0], StringComparison.Ordinal);
        Assert.Contains("Customer testimonial segment.", blocks[1], StringComparison.Ordinal);
        Assert.Contains("Testimonial", blocks[1], StringComparison.Ordinal);
    }
}
