// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 4 / dev plan tasks 4.1 + 4.2 — wraps <see cref="LlmInputHelper.ToLlmInput"/>
/// and strips spurious telemetry lines.
/// </summary>
public sealed class AnalysisRendererTests
{
    private static AnalysisResult MakeInvoiceResult()
    {
        Dictionary<string, ContentField> fields = new(StringComparer.Ordinal)
        {
            ["VendorName"] = ContentUnderstandingModelFactory.ContentStringField(value: "CONTOSO LTD."),
            ["InvoiceDate"] = ContentUnderstandingModelFactory.ContentStringField(value: "2019-11-15"),
        };

        DocumentContent content = ContentUnderstandingModelFactory.DocumentContent(
            mimeType: "application/pdf",
            markdown: "CONTOSO LTD.\n\n# INVOICE\nSome body text.",
            fields: fields,
            startPageNumber: 1,
            endPageNumber: 1);

        return ContentUnderstandingModelFactory.AnalysisResult(contents: [content]);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_default_markdown_and_fields
    public void Render_WithMarkdownAndFields_ContainsBothSections()
    {
        AnalysisResult result = MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Markdown | AnalysisSection.Fields);

        Assert.Contains("source: invoice.pdf", rendered, StringComparison.Ordinal);
        Assert.Contains("fields:", rendered, StringComparison.Ordinal);
        Assert.Contains("VendorName", rendered, StringComparison.Ordinal);
        Assert.Contains("CONTOSO LTD.", rendered, StringComparison.Ordinal);
        Assert.Contains("# INVOICE", rendered, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_markdown_only
    public void Render_MarkdownOnly_OmitsFieldsBlock()
    {
        AnalysisResult result = MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Markdown);

        Assert.Contains("# INVOICE", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("fields:", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("VendorName", rendered, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestOutputFiltering::test_fields_only
    public void Render_FieldsOnly_OmitsMarkdownBody()
    {
        AnalysisResult result = MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Fields);

        Assert.Contains("VendorName", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("# INVOICE", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("Some body text.", rendered, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_include_fields_opt_in (renderer-half override semantics)
    public void Render_IncludeFieldsOverride_WinsOverSectionsFlag()
    {
        AnalysisResult result = MakeInvoiceResult();

        // Sections has Fields, but override forces it off.
        string overrideOff = AnalysisRenderer.Render(
            result, "invoice.pdf", AnalysisSection.Markdown | AnalysisSection.Fields, includeFieldsOverride: false);
        Assert.DoesNotContain("VendorName", overrideOff, StringComparison.Ordinal);

        // Sections lacks Fields, but override forces it on.
        string overrideOn = AnalysisRenderer.Render(
            result, "invoice.pdf", AnalysisSection.Markdown, includeFieldsOverride: true);
        Assert.Contains("VendorName", overrideOn, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestFileSearchIntegration::test_file_search_skips_empty_markdown (renderer-half: empty input → empty output)
    public void Render_EmptyContents_ReturnsEmptyString()
    {
        AnalysisResult empty = ContentUnderstandingModelFactory.AnalysisResult(contents: []);

        string rendered = AnalysisRenderer.Render(empty, "invoice.pdf", AnalysisSection.Default);

        Assert.Equal(string.Empty, rendered);
    }

    [Fact]
    // parity: N/A — .NET-only defensive null-arg guard.
    public void Render_NullResult_Throws()
        => Assert.Throws<ArgumentNullException>(() => AnalysisRenderer.Render(null!, "x.pdf", AnalysisSection.Default));

    [Fact]
    // parity: N/A — .NET-only defensive empty-arg guard.
    public void Render_EmptyFilename_Throws()
    {
        AnalysisResult result = MakeInvoiceResult();
        Assert.Throws<ArgumentException>(() => AnalysisRenderer.Render(result, string.Empty, AnalysisSection.Default));
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestWarningsExtraction::test_llm_stats_telemetry_filtered (in-block strip)
    public void StripTelemetry_RemovesLlmStatsLines_InsideRaiWarnings()
    {
        const string Input =
            "---\n" +
            "contentType: document\n" +
            "source: invoice.pdf\n" +
            "rai_warnings:\n" +
            "  - LLMStats: completion_calls=2; embedding_calls=1; latency=7.71s\n" +
            "  - actual warning: please review\n" +
            "---\n" +
            "# body\n";

        string cleaned = AnalysisRenderer.StripTelemetry(Input);

        Assert.DoesNotContain("LLMStats:", cleaned, StringComparison.Ordinal);
        Assert.Contains("actual warning: please review", cleaned, StringComparison.Ordinal);
        Assert.Contains("# body", cleaned, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestWarningsExtraction::test_llm_stats_telemetry_filtered (trailing-EOF edge)
    public void StripTelemetry_RemovesIndentedLlmStatsAtFileEnd_NoTrailingNewline()
    {
        const string Input = "  - LLMStats: trailing without newline";
        string cleaned = AnalysisRenderer.StripTelemetry(Input);
        Assert.Equal(string.Empty, cleaned);
    }

    [Fact]
    // parity: python tests/cu/test_context_provider.py::TestWarningsExtraction::test_warnings_included_when_present (non-LLMStats survive)
    public void StripTelemetry_LeavesUnrelatedListItemsAlone()
    {
        const string Input =
            "rai_warnings:\n" +
            "  - SomeOtherCategory: hello world\n" +
            "  - LLMStats: nope\n";

        string cleaned = AnalysisRenderer.StripTelemetry(Input);

        Assert.Contains("SomeOtherCategory: hello world", cleaned, StringComparison.Ordinal);
        Assert.DoesNotContain("LLMStats:", cleaned, StringComparison.Ordinal);
    }

    [Fact]
    // parity: N/A — .NET-only empty-input guard.
    public void StripTelemetry_PreservesEmptyInput()
    {
        Assert.Equal(string.Empty, AnalysisRenderer.StripTelemetry(string.Empty));
    }

    [Fact]
    // parity: N/A — .NET-only API contract; Python wires backend via FileSearchConfig presence.
    public void RenderSearchPayload_NullConfig_ReturnsNull()
    {
        AnalysisResult result = MakeInvoiceResult();

        string? payload = AnalysisRenderer.RenderSearchPayload(
            result, "invoice.pdf", AnalysisSection.Markdown | AnalysisSection.Fields, config: null);

        Assert.Null(payload);
    }

    [Fact]
    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_required_fields (include_fields defaults to False)
    public void RenderSearchPayload_ConfigDefault_OmitsFieldsRegardlessOfSections()
    {
        AnalysisResult result = MakeInvoiceResult();
        FileSearchConfig config = new(); // IncludeFields defaults to false

        string? payload = AnalysisRenderer.RenderSearchPayload(
            result, "invoice.pdf", AnalysisSection.Markdown | AnalysisSection.Fields, config);

        Assert.NotNull(payload);
        Assert.DoesNotContain("VendorName", payload!, StringComparison.Ordinal);
        Assert.Contains("# INVOICE", payload!, StringComparison.Ordinal);
    }

    [Fact]
    // parity: python tests/cu/test_models.py::TestFileSearchConfig::test_include_fields_opt_in
    public void RenderSearchPayload_ConfigIncludeFieldsTrue_OverridesSections()
    {
        AnalysisResult result = MakeInvoiceResult();
        FileSearchConfig config = new() { IncludeFields = true };

        // Sections lacks Fields, but FileSearchConfig.IncludeFields = true forces it on.
        string? payload = AnalysisRenderer.RenderSearchPayload(
            result, "invoice.pdf", AnalysisSection.Markdown, config);

        Assert.NotNull(payload);
        Assert.Contains("VendorName", payload!, StringComparison.Ordinal);
    }

    [Fact]
    // parity: N/A — .NET-only assembly-version pin; guards LlmInputHelper upstream contract.
    public void LlmInputHelper_AssemblyVersionMajorMinor_Matches1Dot2()
    {
        Version? v = typeof(LlmInputHelper).Assembly.GetName().Version;
        Assert.NotNull(v);
        Assert.Equal(1, v!.Major);
        Assert.Equal(2, v.Minor);
    }
}
