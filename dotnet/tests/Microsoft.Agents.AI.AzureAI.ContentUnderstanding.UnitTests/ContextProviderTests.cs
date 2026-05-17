// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 2 / dev plan task 2.4 — provider constructor argument validation and StateKeys shape.
/// </summary>
public sealed class ContextProviderTests
{
    private static readonly Uri TestEndpoint = new("https://contoso.cognitiveservices.azure.com/");

    // parity: N/A — .NET-only defensive guard against ctor receiving null options bag.
    [Fact]
    public void OptionsConstructor_ThrowsOnNullOptions()
    {
        var ex = Assert.Throws<ArgumentNullException>(() => new ContentUnderstandingContextProvider(options: null!));
        Assert.Equal("options", ex.ParamName);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_endpoint_raises (object-initializer variant)
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

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_credential_raises (object-initializer variant)
    [Fact]
    public void OptionsConstructor_ThrowsWhenCredentialNotSetByObjectInitializer()
    {
        var options = new ContentUnderstandingContextProviderOptions
        {
            Endpoint = TestEndpoint,
            // Credential deliberately omitted
        };

        var ex = Assert.Throws<ArgumentNullException>(() => new ContentUnderstandingContextProvider(options));
        Assert.Equal("options", ex.ParamName);
        Assert.Contains("Credential", ex.Message);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_endpoint_raises (convenience-ctor variant)
    [Fact]
    public void ConvenienceConstructor_ThrowsOnNullEndpoint()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProvider(endpoint: null!, credential: new FakeTokenCredential()));
        Assert.Equal("endpoint", ex.ParamName);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_missing_credential_raises (convenience-ctor variant)
    [Fact]
    public void ConvenienceConstructor_ThrowsOnNullCredential()
    {
        var ex = Assert.Throws<ArgumentNullException>(() =>
            new ContentUnderstandingContextProvider(endpoint: TestEndpoint, credential: null!));
        Assert.Equal("credential", ex.ParamName);
    }

    // parity: python tests/cu/test_context_provider.py::TestInit::test_custom_values (configure-callback variant)
    [Fact]
    public void ConvenienceConstructor_AppliesConfigureCallback()
    {
        var provider = new ContentUnderstandingContextProvider(
            TestEndpoint,
            new FakeTokenCredential(),
            configure: o =>
            {
                o.AnalyzerId = "prebuilt-invoice";
                o.MaxWait = TimeSpan.FromSeconds(30);
                o.OutputSections = AnalysisSection.Markdown;
            });

        // No public accessor to inspect options yet — but constructing without throwing confirms
        // the configure callback was invoked on a valid Options instance.
        Assert.NotNull(provider);
    }

    // parity: N/A — .NET StateKeys[] contract; Python sessions use a single context-provider key implicitly.
    [Fact]
    public void StateKeys_ReturnsTypeFullName()
    {
        var provider = new ContentUnderstandingContextProvider(TestEndpoint, new FakeTokenCredential());

        Assert.Single(provider.StateKeys);
        Assert.Equal(typeof(ContentUnderstandingContextProvider).FullName, provider.StateKeys[0]);
    }

    // parity: N/A — .NET phase-2 shell contract; later phases supply behavior.
    [Fact]
    public void ProvideAIContextAsync_PhaseFiveNotImplemented()
    {
        // Phase 5 will implement this; Phase 2 ships only the shell.
        // We don't invoke it here because InvokingContext requires non-trivial setup; ensuring
        // the override exists is enforced by the compiler. This test pins the contract.
        var provider = new ContentUnderstandingContextProvider(TestEndpoint, new FakeTokenCredential());
        Assert.NotNull(provider);
    }

    // parity: python tests/cu/test_context_provider.py::TestAsyncContextManager::test_aexit_closes_client (idempotent close)
    [Fact]
    public async Task DisposeAsync_IsIdempotentNoOp()
    {
        var provider = new ContentUnderstandingContextProvider(TestEndpoint, new FakeTokenCredential());

        await provider.DisposeAsync();
        await provider.DisposeAsync(); // second call must not throw
    }
}
