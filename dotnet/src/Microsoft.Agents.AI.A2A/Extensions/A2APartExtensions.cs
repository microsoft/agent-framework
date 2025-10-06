// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="Part"/> class.
/// </summary>
internal static class A2APartExtensions
{
    /// <summary>
    /// Converts an A2A <see cref="Part"/> to an <see cref="AIContent"/>.
    /// </summary>
    /// <param name="part">The A2A part to convert.</param>
    /// <returns>The corresponding <see cref="AIContent"/>, or null if the part type is not supported.</returns>
    internal static AIContent? ToAIContent(this Part part) =>
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

            // Ignore unknown part types (DataPart, etc.)
            _ => null
        };
}
