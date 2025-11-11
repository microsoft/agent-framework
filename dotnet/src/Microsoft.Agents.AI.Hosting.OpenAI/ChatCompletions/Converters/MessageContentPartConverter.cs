// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;

internal static class MessageContentPartConverter
{
    private static string AudioFormatToMediaType(string format) =>
        format.Equals("mp3", StringComparison.OrdinalIgnoreCase) ? "audio/mpeg" :
        format.Equals("wav", StringComparison.OrdinalIgnoreCase) ? "audio/wav" :
        format.Equals("opus", StringComparison.OrdinalIgnoreCase) ? "audio/opus" :
        format.Equals("aac", StringComparison.OrdinalIgnoreCase) ? "audio/aac" :
        format.Equals("flac", StringComparison.OrdinalIgnoreCase) ? "audio/flac" :
        format.Equals("pcm16", StringComparison.OrdinalIgnoreCase) ? "audio/pcm" :
        "audio/*";
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
                    : new UriContent(imagePart.Url, ImageUriToMediaType(imagePart.Url)),

            // audio
            AudioContentPart audioPart =>
                new DataContent(audioPart.InputAudio.Data, AudioFormatToMediaType(audioPart.InputAudio.Format)),

            // file
            FileContentPart filePart when !string.IsNullOrEmpty(filePart.File.FileId)
                => new HostedFileContent(filePart.File.FileId),
            FileContentPart filePart when !string.IsNullOrEmpty(filePart.File.FileData)
                => new DataContent(filePart.File.FileData, "application/octet-stream") { Name = filePart.File.Filename },

            _ => null
        };
    }

    private static string ImageUriToMediaType(Uri uri)
    {
        string absoluteUri = uri.AbsoluteUri;
        return
            absoluteUri.EndsWith(".png", StringComparison.OrdinalIgnoreCase) ? "image/png" :
            absoluteUri.EndsWith(".jpg", StringComparison.OrdinalIgnoreCase) ? "image/jpeg" :
            absoluteUri.EndsWith(".jpeg", StringComparison.OrdinalIgnoreCase) ? "image/jpeg" :
            absoluteUri.EndsWith(".gif", StringComparison.OrdinalIgnoreCase) ? "image/gif" :
            absoluteUri.EndsWith(".bmp", StringComparison.OrdinalIgnoreCase) ? "image/bmp" :
            absoluteUri.EndsWith(".webp", StringComparison.OrdinalIgnoreCase) ? "image/webp" :
            "image/*";
    }
}
