// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Marks a result set as having been numbered by the base <see cref="AgentFileStore.SearchAsync"/>.
/// </summary>
/// <remarks>
/// <para>
/// The alignment check needs to know whether the line numbers it is about to hand to the model came
/// from the base implementation (aligned by construction) or from a store's own
/// <see cref="AgentFileStore.SearchAsync"/>. Reflecting over the store's type is not trim-safe, and a
/// flag on the store would be per instance rather than per call — a store that defers to
/// <c>base.SearchAsync</c> only sometimes would buy permanent trust for the results it numbers itself,
/// which is exactly the failure the check exists to catch.
/// </para>
/// <para>
/// Tagging the returned list keeps the signal with the data. It also fails conservative: an override
/// that copies or post-processes the base results into a new list loses the tag and gets verified.
/// </para>
/// </remarks>
internal sealed class BaseSearchResults(IReadOnlyList<FileSearchResult> results) : List<FileSearchResult>(results);
