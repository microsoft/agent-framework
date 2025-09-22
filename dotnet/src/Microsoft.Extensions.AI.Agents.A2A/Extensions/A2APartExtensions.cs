// Copyright (c) Microsoft. All rights reserved.

using System;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="Part"/> class.
/// </summary>
internal static class A2APartExtensions
{
    /// <summary>
    /// Converts an A2A <see cref="Part"/> to an <see cref="AIContent"/>.
    /// </summary>
    /// <param name="part">The A2A part to convert.</param>
    /// <returns>The corresponding <see cref="AIContent"/>.</returns>
    internal static AIContent ToAIContent(this Part part) =>
        part switch
        {
            TextPart textPart => new TextContent(textPart.Text)
            {
                RawRepresentation = textPart,
                AdditionalProperties = textPart.Metadata.ToAdditionalProperties()
            },

            FilePart filePart when filePart.File is FileWithUri fileWithUrl => new HostedFileContent(fileWithUrl.Uri)
            {
                RawRepresentation = filePart,
                AdditionalProperties = filePart.Metadata.ToAdditionalProperties()
            },

            _ => throw new NotSupportedException($"Part type '{part.GetType().Name}' is not supported.")
        };
}
