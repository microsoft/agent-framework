// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for the <see cref="AIContent"/> class.
/// </summary>
internal static class A2AAIContentExtensions
{
    /// <summary>
    ///  Converts a collection of <see cref="AIContent"/> to a list of <see cref="Part"/> objects.
    /// </summary>
    /// <param name="contents">The collection of AI contents to convert.</param>"
    /// <returns>The list of A2A <see cref="Part"/> objects.</returns>
    internal static List<Part>? ToParts(this IEnumerable<AIContent> contents)
    {
        List<Part>? parts = null;

        foreach (var content in contents)
        {
            var part = content.ToPart();
            if (part is not null)
            {
                (parts ??= []).Add(part);
            }
        }

        return parts;
    }
}
