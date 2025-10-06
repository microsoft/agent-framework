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
    internal static List<Part>? ToA2AParts(this IEnumerable<AIContent> contents)
    {
        List<Part>? parts = null;

        foreach (var content in contents)
        {
            var part = content.ToA2APart();
            if (part is not null)
            {
                (parts ??= []).Add(part);
            }
        }

        return parts;
    }

    /// <summary>
    ///  Converts a <see cref="AIContent"/> to a <see cref="Part"/> object."/>
    /// </summary>
    /// <param name="content">AI content to convert.</param>
    /// <returns>The corresponding A2A <see cref="Part"/> object, or null if the content type is not supported.</returns>
    internal static Part? ToA2APart(this AIContent content) =>
        content switch
        {
            TextContent textContent => new TextPart { Text = textContent.Text },
            HostedFileContent hostedFileContent => new FilePart { File = new FileWithUri { Uri = hostedFileContent.FileId } },
            // Ignore unknown content types (FunctionCallContent, FunctionResultContent, etc.)
            _ => null,
        };
}
