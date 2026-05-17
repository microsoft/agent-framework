// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using Azure.AI.ContentUnderstanding;
using Azure.Core;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Counts how many times <see cref="Create"/> is invoked. Returns the same
/// <see cref="ContentUnderstandingClient"/> instance every time so concurrent callers can be
/// distinguished from accidental re-construction.
/// </summary>
internal sealed class CountingClientFactory : IContentUnderstandingClientFactory
{
    private readonly ContentUnderstandingClient _client;
    private int _count;

    public CountingClientFactory()
    {
        // Real client; constructed lazily by the provider — never makes a network call during
        // the provider's lazy-init test path because the analysis itself is overridden via
        // AnalyzeOverride.
        this._client = new ContentUnderstandingClient(
            new Uri("https://contoso.cognitiveservices.azure.com/"),
            new FakeTokenCredential());
    }

    public int CallCount => Volatile.Read(ref this._count);

    public ContentUnderstandingClient Create()
    {
        Interlocked.Increment(ref this._count);
        return this._client;
    }
}
