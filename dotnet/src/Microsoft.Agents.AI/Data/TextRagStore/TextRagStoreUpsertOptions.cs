// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;

namespace Microsoft.Agents.AI.Data;

/// <summary>
/// Contains options for <see cref="TextRagStore{TKey}.UpsertDocumentsAsync(IEnumerable{TextRagDocument}, TextRagStoreUpsertOptions?, CancellationToken)"/>.
/// </summary>
public sealed class TextRagStoreUpsertOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether the source text should be persisted in the database.
    /// </summary>
    /// <value>
    /// Defaults to <see langword="false"/> if not set.
    /// </value>
    public bool DoNotPersistSourceText { get; init; }
}
