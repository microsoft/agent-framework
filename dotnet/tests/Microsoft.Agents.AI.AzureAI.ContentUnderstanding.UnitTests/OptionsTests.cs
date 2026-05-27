// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.2 — Options class argument validation and defaults.
/// </summary>
public sealed class OptionsTests
{
    private static readonly Uri s_testEndpoint = new("https://contoso.cognitiveservices.azure.com/");

    [Fact]
    public void Constructor_ThrowsOnNullEndpoint()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProviderOptions(endpoint: null!, credential: new FakeTokenCredential()));
        Assert.Equal("endpoint", ex.ParamName);
    }

    [Fact]
    public void Constructor_ThrowsOnNullCredential()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProviderOptions(endpoint: s_testEndpoint, credential: null!));
        Assert.Equal("credential", ex.ParamName);
    }

    [Fact]
    public void Constructor_AssignsRequiredFields()
    {
        var credential = new FakeTokenCredential();
        var options = new ContentUnderstandingContextProviderOptions(s_testEndpoint, credential);

        Assert.Same(s_testEndpoint, options.Endpoint);
        Assert.Same(credential, options.Credential);
    }

    [Fact]
    public void Defaults_MatchDesignDoc()
    {
        var options = new ContentUnderstandingContextProviderOptions(s_testEndpoint, new FakeTokenCredential());

        Assert.Null(options.AnalyzerId);
        Assert.Equal(TimeSpan.FromSeconds(5), options.MaxWait);
        Assert.Equal(AnalysisSection.Default, options.OutputSections);
        Assert.Null(options.FileSearchConfig);
        Assert.Null(options.LoggerFactory);
    }

    [Fact]
    public void ObjectInitializer_CanSetAllProperties()
    {
        var credential = new FakeTokenCredential();
        var options = new ContentUnderstandingContextProviderOptions
        {
            Endpoint = s_testEndpoint,
            Credential = credential,
            AnalyzerId = "prebuilt-invoice",
            MaxWait = TimeSpan.FromSeconds(30),
            OutputSections = AnalysisSection.Markdown,
            FileSearchConfig = new FileSearchConfig(),
        };

        Assert.Same(s_testEndpoint, options.Endpoint);
        Assert.Same(credential, options.Credential);
        Assert.Equal("prebuilt-invoice", options.AnalyzerId);
        Assert.Equal(TimeSpan.FromSeconds(30), options.MaxWait);
        Assert.Equal(AnalysisSection.Markdown, options.OutputSections);
        Assert.NotNull(options.FileSearchConfig);
    }

    // (TimeSpan.Zero is the "no foreground wait" sentinel.)
    [Fact]
    public void MaxWait_CanBeSetToZero_ToForceImmediateBackgroundDefer()
    {
        var options = new ContentUnderstandingContextProviderOptions(s_testEndpoint, new FakeTokenCredential())
        {
            MaxWait = TimeSpan.Zero,
        };

        Assert.Equal(TimeSpan.Zero, options.MaxWait);
    }
}
