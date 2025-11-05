// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Extension methods for <see cref="SortOrder"/>.
/// </summary>
internal static class SortOrderExtensions
{
    /// <summary>
    /// Converts a <see cref="SortOrder"/> to its string representation.
    /// </summary>
    /// <param name="order">The sort order.</param>
    /// <returns>The string representation ("asc" or "desc").</returns>
    public static string ToOrderString(this SortOrder order)
    {
        return order == SortOrder.Ascending ? "asc" : "desc";
    }

    /// <summary>
    /// Checks if the sort order is ascending.
    /// </summary>
    /// <param name="order">The sort order.</param>
    /// <returns>True if ascending, false otherwise.</returns>
    public static bool IsAscending(this SortOrder order)
    {
        return order == SortOrder.Ascending;
    }
}
