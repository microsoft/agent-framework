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
    public void Render_MarkdownOnly_OmitsFieldsBlock()
    {
        AnalysisResult result = MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Markdown);

        Assert.Contains("# INVOICE", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("fields:", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("VendorName", rendered, StringComparison.Ordinal);
    }

    [Fact]
    public void Render_FieldsOnly_OmitsMarkdownBody()
    {
        AnalysisResult result = MakeInvoiceResult();

        string rendered = AnalysisRenderer.Render(result, "invoice.pdf", AnalysisSection.Fields);

        Assert.Contains("VendorName", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("# INVOICE", rendered, StringComparison.Ordinal);
        Assert.DoesNotContain("Some body text.", rendered, StringComparison.Ordinal);
    }

    [Fact]
    public void Render_EmptyContents_ReturnsEmptyString()
    {
        AnalysisResult empty = ContentUnderstandingModelFactory.AnalysisResult(contents: []);

        string rendered = AnalysisRenderer.Render(empty, "invoice.pdf", AnalysisSection.Default);

        Assert.Equal(string.Empty, rendered);
    }

    [Fact]
    public void Render_NullResult_Throws()
        => Assert.Throws<ArgumentNullException>(() => AnalysisRenderer.Render(null!, "x.pdf", AnalysisSection.Default));

    [Fact]
    public void Render_EmptyFilename_Throws()
    {
        AnalysisResult result = MakeInvoiceResult();
        Assert.Throws<ArgumentException>(() => AnalysisRenderer.Render(result, string.Empty, AnalysisSection.Default));
    }

    [Fact]
    public void LlmInputHelper_AssemblyVersionMajorMinor_Matches1Dot2()
    {
        Version? v = typeof(LlmInputHelper).Assembly.GetName().Version;
        Assert.NotNull(v);
        Assert.Equal(1, v!.Major);
        Assert.Equal(2, v.Minor);
    }
}
