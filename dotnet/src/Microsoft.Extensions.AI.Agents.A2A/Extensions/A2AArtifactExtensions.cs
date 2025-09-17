// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="Artifact"/> class.
/// </summary>
internal static class A2AArtifactExtensions
{
    /// <summary>
    /// Converts an A2A <see cref="Artifact"/> to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="artifact">The A2A artifact to convert.</param>
    /// <param name="authorName">The author name to set on the resulting <see cref="ChatMessage"/>.</param>
    /// <returns>The corresponding <see cref="ChatMessage"/>.</returns>
    public static ChatMessage ToChatMessage(this Artifact artifact, string? authorName = null)
    {
        return new ChatMessage(ChatRole.Assistant, [.. artifact.Parts.Select(part => part.ToAIContent())])
        {
            AuthorName = authorName,
            RawRepresentation = artifact,
            AdditionalProperties = AddArtifactPropertiesAsAdditionalProperties(artifact),
        };
    }

    /// <summary>
    /// Converts an A2A <see cref="Artifact"/> to a list of <see cref="AIContent"/>.
    /// </summary>
    /// <param name="artifact">The A2A artifact to convert.</param>
    /// <returns>The corresponding list of <see cref="AIContent"/>.</returns>
    public static List<AIContent> ToAIContents(this Artifact artifact)
    {
        List<AIContent> contents = [];

        foreach (var part in artifact.Parts)
        {
            var aiContent = part.ToAIContent();

            aiContent.AdditionalProperties = AddArtifactPropertiesAsAdditionalProperties(artifact);

            contents.Add(aiContent);
        }

        return contents;
    }

    /// <summary>
    /// Converts a list of A2A <see cref="Artifact"/> to a list of <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="artifacts">The A2A artifacts to convert and add as chat messages.</param>
    /// <param name="taskStatus">The current status of the task producing the artifacts.</param>
    /// <param name="authorName">The author name to set on the resulting <see cref="ChatMessage"/>.</param>
    /// <returns>The corresponding list of <see cref="ChatMessage"/>.</returns>
    internal static IList<ChatMessage> ToChatMessages(this IList<Artifact>? artifacts, AgentTaskStatus taskStatus, string? authorName = null)
    {
        List<ChatMessage>? chatMessages = null;

        // If the task is waiting for user input, add a TextInputRequestContent message first.
        if (taskStatus.State == TaskState.InputRequired)
        {
            ChatMessage chatMessage = new(ChatRole.Assistant, taskStatus.GetUserInputRequests())
            {
                AuthorName = authorName,
                Role = ChatRole.Assistant,
            };

            (chatMessages ??= []).Add(chatMessage);
        }

        if (artifacts is null || artifacts.Count == 0)
        {
            return chatMessages ?? [];
        }

        foreach (var artifact in artifacts)
        {
            (chatMessages ??= []).Add(artifact.ToChatMessage(authorName));
        }

        return chatMessages ?? [];
    }

    private static AdditionalPropertiesDictionary AddArtifactPropertiesAsAdditionalProperties(Artifact artifact)
    {
        var additionalProperties = artifact.Metadata.ToAdditionalProperties() ?? [];

        additionalProperties[nameof(Artifact.ArtifactId)] = artifact.ArtifactId;

        if (!string.IsNullOrWhiteSpace(artifact.Name))
        {
            additionalProperties[nameof(Artifact.Name)] = artifact.Name!;
        }

        if (!string.IsNullOrWhiteSpace(artifact.Description))
        {
            additionalProperties[nameof(Artifact.Description)] = artifact.Description!;
        }

        if (artifact.Extensions is { Count: > 0 })
        {
            additionalProperties[nameof(Artifact.Extensions)] = artifact.Extensions;
        }

        return additionalProperties;
    }
}
