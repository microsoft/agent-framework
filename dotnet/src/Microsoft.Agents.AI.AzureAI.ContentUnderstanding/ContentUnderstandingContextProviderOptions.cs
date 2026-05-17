// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Options for <see cref="ContentUnderstandingContextProvider"/>.
/// </summary>
/// <remarks>
/// Two constructors are provided: a parameterless one for object-initializer usage
/// (<c>new Options { Endpoint = ..., Credential = ... }</c>), and a parameterized one that
/// validates the required <see cref="Endpoint"/> and <see cref="Credential"/> at construction
/// time. Properties use <c>set;</c> rather than <c>init;</c> so the convenience constructor
/// on <see cref="ContentUnderstandingContextProvider"/> can apply post-construction mutations
/// via its <c>Action&lt;Options&gt; configure</c> callback. The provider revalidates
/// <see cref="Endpoint"/> and <see cref="Credential"/> defensively for the object-initializer path.
/// See <c>features/sdk/dotnet-cu-context-provider/design-doc-dotnet-cu-context-provider.md</c>
/// "API Surface".
/// </remarks>
public sealed class ContentUnderstandingContextProviderOptions
{
    /// <summary>
    /// Initializes an empty options object for use with an object initializer.
    /// </summary>
    /// <remarks>
    /// <see cref="Endpoint"/> and <see cref="Credential"/> must be assigned before the options
    /// are passed to <see cref="ContentUnderstandingContextProvider"/>.
    /// </remarks>
    public ContentUnderstandingContextProviderOptions()
    {
    }

    /// <summary>
    /// Initializes options with the required <see cref="Endpoint"/> and <see cref="Credential"/>.
    /// </summary>
    /// <param name="endpoint">The Content Understanding service endpoint.</param>
    /// <param name="credential">The credential used to authenticate against the service.</param>
    /// <exception cref="ArgumentNullException"><paramref name="endpoint"/> or <paramref name="credential"/> is <see langword="null"/>.</exception>
    public ContentUnderstandingContextProviderOptions(Uri endpoint, TokenCredential credential)
    {
        this.Endpoint = endpoint ?? throw new ArgumentNullException(nameof(endpoint));
        this.Credential = credential ?? throw new ArgumentNullException(nameof(credential));
    }

    /// <summary>The Content Understanding service endpoint. Required.</summary>
    public Uri Endpoint { get; set; } = default!;

    /// <summary>The credential used to authenticate against the service. Required.</summary>
    public TokenCredential Credential { get; set; } = default!;

    /// <summary>
    /// Explicit Content Understanding analyzer id to use for every attachment. When
    /// <see langword="null"/>, the provider auto-selects based on media type
    /// (<c>prebuilt-documentSearch</c> / <c>prebuilt-audioSearch</c> / <c>prebuilt-videoSearch</c>).
    /// </summary>
    public string? AnalyzerId { get; set; }

    /// <summary>
    /// Maximum wall-clock time to wait for a Content Understanding analysis to complete inline
    /// before falling back to background continuation. Default: 5 seconds.
    /// </summary>
    public TimeSpan MaxWait { get; set; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// Selects which sections of the analysis result are rendered into the LLM-facing text.
    /// Default: <see cref="AnalysisSection.Default"/> (markdown + fields).
    /// </summary>
    public AnalysisSection OutputSections { get; set; } = AnalysisSection.Default;

    /// <summary>
    /// Optional vector-store / file_search integration. When set, ready documents are uploaded
    /// to the configured vector store and the caller-supplied <c>file_search</c> tool is
    /// surfaced; the rendered markdown is not injected into <c>AIContext.Messages</c>.
    /// </summary>
    public FileSearchConfig? FileSearchConfig { get; set; }

    /// <summary>Optional logger factory; used to wire Content Understanding client diagnostics.</summary>
    public ILoggerFactory? LoggerFactory { get; set; }
}
