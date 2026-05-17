// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.1 — public enum shapes.
/// </summary>
public sealed class ModelsTests
{
    // parity: N/A — .NET-only flags-enum shape; Python uses string literals.
    [Fact]
    public void AnalysisSection_Default_IsMarkdownPlusFields()
    {
        Assert.Equal(AnalysisSection.Markdown | AnalysisSection.Fields, AnalysisSection.Default);
    }

    // parity: N/A — .NET-only flags-enum shape.
    [Fact]
    public void AnalysisSection_None_IsZero()
    {
        Assert.Equal((AnalysisSection)0, AnalysisSection.None);
    }

    // parity: N/A — .NET-only flags-enum shape.
    [Fact]
    public void AnalysisSection_FlagsAreDistinctPowersOfTwo()
    {
        Assert.Equal(1, (int)AnalysisSection.Markdown);
        Assert.Equal(2, (int)AnalysisSection.Fields);
    }

    // parity: python tests/cu/test_models.py::TestDocumentEntry::test_construction (status enum shape)
    [Fact]
    public void DocumentStatus_EnumeratesExpectedValues()
    {
        var values = (DocumentStatus[])Enum.GetValues(typeof(DocumentStatus));
        Assert.Equal(
            new[] { DocumentStatus.Analyzing, DocumentStatus.Uploading, DocumentStatus.Ready, DocumentStatus.Failed },
            values);
    }
}
