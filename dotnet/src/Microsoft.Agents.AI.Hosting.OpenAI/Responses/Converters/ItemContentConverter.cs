// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Provides bidirectional conversion between <see cref="AIContent"/> and <see cref="ItemContent"/> types.
/// </summary>
internal static class ItemContentConverter
{
    private static string AudioFormatToMediaType(string? format) =>
        format?.Equals("mp3", StringComparison.OrdinalIgnoreCase) == true ? "audio/mpeg" :
        format?.Equals("wav", StringComparison.OrdinalIgnoreCase) == true ? "audio/wav" :
        format?.Equals("opus", StringComparison.OrdinalIgnoreCase) == true ? "audio/opus" :
        format?.Equals("aac", StringComparison.OrdinalIgnoreCase) == true ? "audio/aac" :
        format?.Equals("flac", StringComparison.OrdinalIgnoreCase) == true ? "audio/flac" :
        format?.Equals("pcm16", StringComparison.OrdinalIgnoreCase) == true ? "audio/pcm" :
        "audio/*";

    private static string MediaTypeToAudioFormat(string mediaType) =>
        mediaType.Equals("audio/mpeg", StringComparison.OrdinalIgnoreCase) ? "mp3" :
        mediaType.Equals("audio/wav", StringComparison.OrdinalIgnoreCase) ? "wav" :
        mediaType.Equals("audio/opus", StringComparison.OrdinalIgnoreCase) ? "opus" :
        mediaType.Equals("audio/aac", StringComparison.OrdinalIgnoreCase) ? "aac" :
        mediaType.Equals("audio/flac", StringComparison.OrdinalIgnoreCase) ? "flac" :
        mediaType.Equals("audio/pcm", StringComparison.OrdinalIgnoreCase) ? "pcm16" :
        "mp3";
    /// <summary>
    /// Converts <see cref="ItemContent"/> to <see cref="AIContent"/>.
    /// </summary>
    /// <param name="itemContent">The <see cref="ItemContent"/> to convert.</param>
    /// <returns>An <see cref="AIContent"/> object, or null if the content cannot be converted.</returns>
    public static AIContent? ToAIContent(ItemContent itemContent)
    {
        // Check if we already have the raw representation to avoid unnecessary conversion
        if (itemContent.RawRepresentation is AIContent rawContent)
        {
            return rawContent;
        }

        AIContent? aiContent = itemContent switch
        {
            // Text content
            ItemContentInputText inputText => new TextContent(inputText.Text),
            ItemContentOutputText outputText => new TextContent(outputText.Text),

            // Error/refusal content
            ItemContentRefusal refusal => new ErrorContent(refusal.Refusal),

            // Image content
            ItemContentInputImage inputImage when !string.IsNullOrEmpty(inputImage.ImageUrl) =>
                inputImage.ImageUrl!.StartsWith("data:", StringComparison.OrdinalIgnoreCase)
                    ? new DataContent(inputImage.ImageUrl, "image/*")
                    : new UriContent(inputImage.ImageUrl, "image/*"),
            ItemContentInputImage inputImage when !string.IsNullOrEmpty(inputImage.FileId) =>
                new HostedFileContent(inputImage.FileId!),

            // File content
            ItemContentInputFile inputFile when !string.IsNullOrEmpty(inputFile.FileId) =>
                new HostedFileContent(inputFile.FileId!),
            ItemContentInputFile inputFile when !string.IsNullOrEmpty(inputFile.FileData) =>
                new DataContent(inputFile.FileData!, "application/octet-stream"),

            // Audio content - map to DataContent with media type based on format
            ItemContentInputAudio inputAudio =>
                new DataContent(inputAudio.Data, AudioFormatToMediaType(inputAudio.Format)),
            ItemContentOutputAudio outputAudio =>
                new DataContent(outputAudio.Data, "audio/*"),

            _ => null
        };

        if (aiContent is not null)
        {
            // Add image detail to additional properties if present
            if (itemContent is ItemContentInputImage { Detail: not null } image)
            {
                (aiContent.AdditionalProperties ??= [])["detail"] = image.Detail;
            }

            // Preserve the original <see cref="ItemContent"/> as raw representation for round-tripping
            aiContent.RawRepresentation = itemContent;
        }

        return aiContent;
    }

    /// <summary>
    /// Converts <see cref="AIContent"/> to <see cref="ItemContent"/> for output messages.
    /// </summary>
    /// <param name="content">The AI content to convert.</param>
    /// <returns>An <see cref="ItemContent"/> object, or null if the content cannot be converted.</returns>
    public static ItemContent? ToItemContent(AIContent content)
    {
        // Check if we already have the raw representation to avoid unnecessary conversion
        if (content.RawRepresentation is ItemContent itemContent)
        {
            return itemContent;
        }

        ItemContent? result = content switch
        {
            TextContent textContent => new ItemContentOutputText { Text = textContent.Text ?? string.Empty, Annotations = [], Logprobs = [] },
            TextReasoningContent reasoningContent => new ItemContentOutputText { Text = reasoningContent.Text ?? string.Empty, Annotations = [], Logprobs = [] },
            ErrorContent errorContent => new ItemContentRefusal { Refusal = errorContent.Message ?? string.Empty },
            UriContent uriContent when uriContent.HasTopLevelMediaType("image") =>
                new ItemContentInputImage
                {
                    ImageUrl = uriContent.Uri?.ToString(),
                    Detail = GetImageDetail(uriContent)
                },
            HostedFileContent hostedFile =>
                new ItemContentInputFile
                {
                    FileId = hostedFile.FileId
                },
            DataContent dataContent when dataContent.HasTopLevelMediaType("image") =>
                new ItemContentInputImage
                {
                    ImageUrl = dataContent.Uri,
                    Detail = GetImageDetail(dataContent)
                },
            DataContent audioData when audioData.HasTopLevelMediaType("audio") =>
                new ItemContentInputAudio
                {
                    Data = audioData.Uri,
                    Format = MediaTypeToAudioFormat(audioData.MediaType)
                },
            DataContent fileData =>
                new ItemContentInputFile
                {
                    FileData = fileData.Uri,
                    Filename = fileData.Name
                },
            // Other AIContent types (FunctionCallContent, FunctionResultContent, etc.)
            // are handled separately in the Responses API as different ItemResource types, not ItemContent
            _ => null
        };

        result?.RawRepresentation = content;

        return result;
    }

    /// <summary>
    /// Extracts the image detail level from <see cref="AIContent"/>'s additional properties.
    /// </summary>
    /// <param name="content">The <see cref="AIContent"/> to extract detail from.</param>
    /// <returns>The detail level as a string, or null if not present.</returns>
    private static string? GetImageDetail(AIContent content)
    {
        if (content.AdditionalProperties?.TryGetValue("detail", out object? value) is true)
        {
            return value?.ToString();
        }

        return null;
    }
}
