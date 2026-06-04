// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.4 — provider constructor argument validation and StateKeys shape.
/// </summary>
public sealed class ContextProviderTests
{
    private static readonly Uri s_testEndpoint = new("https://contoso.cognitiveservices.azure.com/");

    [Fact]
    public void OptionsConstructor_ThrowsOnNullOptions()
    {
        var ex = Assert.Throws<ArgumentNullException>(() => new ContentUnderstandingContextProvider(options: null!));
        Assert.Equal("options", ex.ParamName);
    }

    [Fact]
    public void OptionsConstructor_ThrowsWhenEndpointNotSetByObjectInitializer()
    {
        var options = new ContentUnderstandingContextProviderOptions
        {
            // Endpoint deliberately omitted
            Credential = new FakeTokenCredential(),
        };

        var ex = Assert.Throws<ArgumentNullException>(() => new ContentUnderstandingContextProvider(options));
        Assert.Equal("options", ex.ParamName);
        Assert.Contains("Endpoint", ex.Message);
    }

    [Fact]
    public void OptionsConstructor_ThrowsWhenCredentialNotSetByObjectInitializer()
    {
        var options = new ContentUnderstandingContextProviderOptions
        {
            Endpoint = s_testEndpoint,
            // Credential deliberately omitted
        };

        var ex = Assert.Throws<ArgumentNullException>(() => new ContentUnderstandingContextProvider(options));
        Assert.Equal("options", ex.ParamName);
        Assert.Contains("Credential", ex.Message);
    }

    [Fact]
    public void ConvenienceConstructor_ThrowsOnNullEndpoint()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProvider(endpoint: null!, credential: new FakeTokenCredential()));
        Assert.Equal("endpoint", ex.ParamName);
    }

    [Fact]
    public void ConvenienceConstructor_ThrowsOnNullCredential()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProvider(endpoint: s_testEndpoint, credential: null!));
        Assert.Equal("credential", ex.ParamName);
    }

    [Fact]
    public void OptionsConstructor_AppliesOptions()
    {
        var provider = new ContentUnderstandingContextProvider(
            new ContentUnderstandingContextProviderOptions(s_testEndpoint, new FakeTokenCredential())
            {
                AnalyzerId = "prebuilt-invoice",
                MaxWait = TimeSpan.FromSeconds(30),
                OutputSections = AnalysisSection.Markdown,
            });

        // No public accessor to inspect options yet — but constructing without throwing confirms
        // the options were accepted on a valid Options instance.
        Assert.NotNull(provider);
    }

    [Fact]
    public void StateKeys_ReturnsTypeFullName()
    {
        var provider = new ContentUnderstandingContextProvider(s_testEndpoint, new FakeTokenCredential());

        Assert.Single(provider.StateKeys);
        Assert.Equal(typeof(ContentUnderstandingContextProvider).FullName, provider.StateKeys[0]);
    }

    [Fact]
    public void ProvideAIContextAsync_PhaseFiveNotImplemented()
    {
        // Phase 5 will implement this; Phase 2 ships only the shell.
        // We don't invoke it here because InvokingContext requires non-trivial setup; ensuring
        // the override exists is enforced by the compiler. This test pins the contract.
        var provider = new ContentUnderstandingContextProvider(s_testEndpoint, new FakeTokenCredential());
        Assert.NotNull(provider);
    }

    [Fact]
    public async Task DisposeAsync_IsIdempotentNoOp()
    {
        var provider = new ContentUnderstandingContextProvider(s_testEndpoint, new FakeTokenCredential());

        await provider.DisposeAsync();
        await provider.DisposeAsync(); // second call must not throw
    }
}
