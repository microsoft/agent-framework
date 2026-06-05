// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Creates the <see cref="ContentUnderstandingClient"/> the provider lazily binds on the
/// first analysis request. Exposed as an internal seam so unit tests can substitute a
/// fake (and count construction calls for the lazy-init idempotency assertion).
/// </summary>
internal interface IContentUnderstandingClientFactory
{
    ContentUnderstandingClient Create();
}

internal sealed class DefaultContentUnderstandingClientFactory : IContentUnderstandingClientFactory
{
    private readonly ContentUnderstandingContextProviderOptions _options;

    public DefaultContentUnderstandingClientFactory(ContentUnderstandingContextProviderOptions options)
    {
        this._options = options ?? throw new ArgumentNullException(nameof(options));
    }

    public ContentUnderstandingClient Create()
    {
        if (this._options.Endpoint is null)
        {
            throw new InvalidOperationException($"{nameof(ContentUnderstandingContextProviderOptions)}.{nameof(this._options.Endpoint)} must be set before creating the client.");
        }

        if (!Uri.TryCreate(this._options.Endpoint, UriKind.Absolute, out _))
        {
            throw new InvalidOperationException($"{nameof(ContentUnderstandingContextProviderOptions)}.{nameof(this._options.Endpoint)} must be a valid absolute URI, but was: '{this._options.Endpoint}'.");
        }

        if (this._options.Credential is null)
        {
            throw new InvalidOperationException($"{nameof(ContentUnderstandingContextProviderOptions)}.{nameof(this._options.Credential)} must be set before creating the client.");
        }

        return new(this._options.Endpoint, this._options.Credential);
    }
}
