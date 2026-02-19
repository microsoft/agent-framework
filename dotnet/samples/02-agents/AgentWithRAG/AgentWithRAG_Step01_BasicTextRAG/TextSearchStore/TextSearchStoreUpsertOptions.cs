// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Samples;

/// <summary>
/// Contains options for <see cref="TextSearchStore.UpsertDocumentsAsync(IEnumerable{TextSearchDocument}, TextSearchStoreUpsertOptions?, CancellationToken)"/>.
/// </summary>
public sealed class TextSearchStoreUpsertOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether the source text should be persisted in the database.
    /// </summary>
    /// <value>
    /// Defaults to <see langword="false"/> if not set.
    /// </value>
    public bool DoNotPersistSourceText { get; init; }
}
