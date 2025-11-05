// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

internal static class TestHelpers
{
    /// <summary>
    /// Extension method to convert a synchronous enumerable to an async enumerable for testing purposes.
    /// </summary>
    public static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(this IEnumerable<T> source)
    {
        foreach (T item in source)
        {
            yield return item;
            await Task.CompletedTask;
        }
    }
}
