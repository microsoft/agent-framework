// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a vector store that is hosted by the AI service.
/// </summary>
/// <remarks>
/// Unlike <see cref="DataContent"/> which contains the data for a file or blob, this class represents a vector store that is hosted
/// by the AI service and referenced by an identifier. Such identifiers are specific to the provider.
/// </remarks>
[DebuggerDisplay("VectorStoreId = {VectorStoreId}")]
[ExcludeFromCodeCoverage]
public sealed class HostedVectorStoreContent : AIContent
{
    private string? _vectorStoreId;

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedVectorStoreContent"/> class.
    /// </summary>
    /// <param name="vectorStoreId">The ID of the hosted vector store.</param>
    /// <exception cref="ArgumentNullException"><paramref name="vectorStoreId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="vectorStoreId"/> is empty or composed entirely of whitespace.</exception>
    public HostedVectorStoreContent(string vectorStoreId)
    {
        _vectorStoreId = Throw.IfNullOrWhitespace(vectorStoreId);
    }

    /// <summary>
    /// Gets or sets the ID of the hosted vector store.
    /// </summary>
    /// <exception cref="ArgumentNullException"><paramref name="value"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="value"/> is empty or composed entirely of whitespace.</exception>
    public string VectorStoreId
    {
        get => _vectorStoreId ?? string.Empty;
        set => _vectorStoreId = Throw.IfNullOrWhitespace(value);
    }
}
