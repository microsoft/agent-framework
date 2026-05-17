// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using OpenAI.Files;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// <see cref="FileSearchBackend"/> implementation backed by an <see cref="AIProjectClient"/>'s
/// OpenAI-compatible sub-client. Uploads use <c>FileUploadPurpose.Assistants</c>
/// (Foundry's required value for the <c>file_search</c> tool).
/// </summary>
/// <remarks>
/// <para>
/// Use this backend when the agent is wired through <c>FoundryChatClient</c> (Azure AI Foundry
/// project). Vector store creation and the <c>file_search</c> tool itself remain
/// caller-managed; this backend only handles file upload / indexing-poll / delete.
/// </para>
/// <para>Mirrors Python <c>FoundryFileSearchBackend</c>.</para>
/// </remarks>
public sealed class FoundryFileSearchBackend : OpenAICompatFileSearchBackendBase
{
    /// <summary>
    /// Initializes a new <see cref="FoundryFileSearchBackend"/> from an existing
    /// <see cref="AIProjectClient"/>. The project's OpenAI-compatible sub-client
    /// (<see cref="AIProjectClient.ProjectOpenAIClient"/>) is captured eagerly.
    /// </summary>
    /// <param name="projectClient">An authenticated Foundry project client.</param>
    /// <exception cref="ArgumentNullException"><paramref name="projectClient"/> is <see langword="null"/>.</exception>
    public FoundryFileSearchBackend(AIProjectClient projectClient)
        : base((projectClient ?? throw new ArgumentNullException(nameof(projectClient))).ProjectOpenAIClient)
    {
    }

    /// <inheritdoc/>
    protected override FileUploadPurpose Purpose
    {
        get
        {
#pragma warning disable OPENAI001 // FileUploadPurpose.Assistants is experimental in OpenAI 2.10.
            return FileUploadPurpose.Assistants;
#pragma warning restore OPENAI001
        }
    }
}
