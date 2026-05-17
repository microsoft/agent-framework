// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.2 — Options class argument validation and defaults.
/// </summary>
public sealed class OptionsTests
{
    private static readonly Uri TestEndpoint = new("https://contoso.cognitiveservices.azure.com/");

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_endpoint_raises
    [Fact]
    public void Constructor_ThrowsOnNullEndpoint()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProviderOptions(endpoint: null!, credential: new FakeTokenCredential()));
        Assert.Equal("endpoint", ex.ParamName);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_credential_raises
    [Fact]
    public void Constructor_ThrowsOnNullCredential()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProviderOptions(endpoint: TestEndpoint, credential: null!));
        Assert.Equal("credential", ex.ParamName);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_custom_values (partial — covers required-field assignment)
    [Fact]
    public void Constructor_AssignsRequiredFields()
    {
        var credential = new FakeTokenCredential();
        var options = new ContentUnderstandingContextProviderOptions(TestEndpoint, credential);

        Assert.Same(TestEndpoint, options.Endpoint);
        Assert.Same(credential, options.Credential);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_default_values
    [Fact]
    public void Defaults_MatchDesignDoc()
    {
        var options = new ContentUnderstandingContextProviderOptions(TestEndpoint, new FakeTokenCredential());

        Assert.Null(options.AnalyzerId);
        Assert.Equal(TimeSpan.FromSeconds(5), options.MaxWait);
        Assert.Equal(AnalysisSection.Default, options.OutputSections);
        Assert.Null(options.FileSearchConfig);
        Assert.Null(options.LoggerFactory);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_custom_values
    [Fact]
    public void ObjectInitializer_CanSetAllProperties()
    {
        var credential = new FakeTokenCredential();
        var options = new ContentUnderstandingContextProviderOptions
        {
            Endpoint = TestEndpoint,
            Credential = credential,
            AnalyzerId = "prebuilt-invoice",
            MaxWait = TimeSpan.FromSeconds(30),
            OutputSections = AnalysisSection.Markdown,
            FileSearchConfig = new FileSearchConfig(),
        };

        Assert.Same(TestEndpoint, options.Endpoint);
        Assert.Same(credential, options.Credential);
        Assert.Equal("prebuilt-invoice", options.AnalyzerId);
        Assert.Equal(TimeSpan.FromSeconds(30), options.MaxWait);
        Assert.Equal(AnalysisSection.Markdown, options.OutputSections);
        Assert.NotNull(options.FileSearchConfig);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_max_wait_none
    // (.NET uses TimeSpan.Zero as the "no foreground wait" sentinel where Python passes None.)
    [Fact]
    public void MaxWait_CanBeSetToZero_ToForceImmediateBackgroundDefer()
    {
        var options = new ContentUnderstandingContextProviderOptions(TestEndpoint, new FakeTokenCredential())
        {
            MaxWait = TimeSpan.Zero,
        };

        Assert.Equal(TimeSpan.Zero, options.MaxWait);
    }
}
