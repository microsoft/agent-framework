// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;

internal static class MessageContentPartConverter
{
    public static AIContent? ToAIContent(MessageContentPart part)
    {
        return part switch
        {
            // text
            TextContentPart textPart => new TextContent(textPart.Text),

            // image
            ImageContentPart imagePart when !string.IsNullOrEmpty(imagePart.UrlOrData) =>
                imagePart.UrlOrData.StartsWith("data:", StringComparison.OrdinalIgnoreCase)
                    ? new DataContent(imagePart.UrlOrData, "image/*")
                    : new UriContent(imagePart.UrlOrData, "image/*"),

            // audio
            AudioContentPart audioPart =>
                new DataContent(audioPart.InputAudio.Data, audioPart.InputAudio.Format.ToUpperInvariant() switch
                {
                    // only MP3 or WAV are supported
                    "MP3" => "audio/mpeg",
                    "WAV" => "audio/wav",
                    _ => "audio/*"
                }),

            // file
            FileContentPart filePart when !string.IsNullOrEmpty(filePart.File.FileId)
                => new HostedFileContent(filePart.File.FileId),
            FileContentPart filePart when !string.IsNullOrEmpty(filePart.File.FileData)
                => new DataContent(filePart.File.FileData, "application/octet-stream") { Name = filePart.File.Filename },

            _ => null
        };
    }
}
