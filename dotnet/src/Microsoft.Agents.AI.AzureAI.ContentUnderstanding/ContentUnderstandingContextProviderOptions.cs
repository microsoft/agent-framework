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
/// time. Properties use <c>init;</c> so options are immutable once constructed. The provider
/// revalidates <see cref="Endpoint"/> and <see cref="Credential"/> defensively for the
/// object-initializer path.
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
    public Uri Endpoint { get; init; } = default!;

    /// <summary>The credential used to authenticate against the service. Required.</summary>
    public TokenCredential Credential { get; init; } = default!;

    /// <summary>
    /// Explicit Content Understanding analyzer id to use for every attachment. When
    /// <see langword="null"/>, the provider auto-selects based on media type
    /// (<c>prebuilt-documentSearch</c> / <c>prebuilt-audioSearch</c> / <c>prebuilt-videoSearch</c>).
    /// </summary>
    public string? AnalyzerId { get; init; }

    /// <summary>
    /// Maximum wall-clock time to wait for a Content Understanding analysis to complete inline
    /// before deferring to the next turn. When the inline attempt times out, the provider
    /// stores a rehydration token and re-polls the operation at the start of the next call to
    /// the same provider instance. Default: 5 seconds.
    /// </summary>
    public TimeSpan MaxWait { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// Selects which sections of the analysis result are rendered into the LLM-facing text.
    /// Default: <see cref="AnalysisSection.Default"/> (markdown + fields).
    /// </summary>
    public AnalysisSection OutputSections { get; init; } = AnalysisSection.Default;

    /// <summary>
    /// How the provider's per-document registry is scoped. Default
    /// <see cref="StateScope.PerSession"/> isolates state per <c>AgentSession</c> and is the
    /// correct choice when a single provider instance serves multiple users. Set to
    /// <see cref="StateScope.PerAgent"/> in hosting scenarios where the layer creates a fresh
    /// <c>AgentSession</c> per HTTP request (e.g. the OpenAI Responses host without server-side
    /// conversation storage) — without it the provider would lose its document cache between
    /// turns.
    /// </summary>
    public StateScope StateScope { get; init; } = StateScope.PerSession;

    /// <summary>
    /// Optional vector-store / file_search integration. When set, ready documents are uploaded
    /// to the configured vector store and the caller-supplied <c>file_search</c> tool is
    /// surfaced; the rendered markdown is not injected into <c>AIContext.Messages</c>.
    /// </summary>
    public FileSearchConfig? FileSearchConfig { get; init; }

    /// <summary>Optional logger factory; used to wire Content Understanding client diagnostics.</summary>
    public ILoggerFactory? LoggerFactory { get; init; }
}
