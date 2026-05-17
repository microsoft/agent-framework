// Copyright (c) Microsoft. All rights reserved.

using OpenAI;
using OpenAI.Files;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// <see cref="FileSearchBackend"/> implementation backed by a raw
/// <see cref="OpenAIClient"/>. Uploads use <c>FileUploadPurpose.UserData</c>
/// (OpenAI's required value for the Responses API <c>file_search</c> tool).
/// </summary>
/// <remarks>
/// <para>
/// Use this backend when the agent is wired through a direct <see cref="OpenAIClient"/>
/// (e.g. <c>OpenAIChatClient</c>). Vector store creation and the <c>file_search</c> tool
/// itself remain caller-managed; this backend only handles file upload / indexing-poll /
/// delete.
/// </para>
/// <para>Mirrors Python <c>OpenAIFileSearchBackend</c>.</para>
/// </remarks>
public sealed class OpenAIFileSearchBackend : OpenAICompatFileSearchBackendBase
{
    /// <summary>
    /// Initializes a new <see cref="OpenAIFileSearchBackend"/> from an authenticated
    /// <see cref="OpenAIClient"/>.
    /// </summary>
    /// <param name="openAiClient">An OpenAI client.</param>
    /// <exception cref="ArgumentNullException"><paramref name="openAiClient"/> is <see langword="null"/>.</exception>
    public OpenAIFileSearchBackend(OpenAIClient openAiClient)
        : base(openAiClient)
    {
    }

    /// <inheritdoc/>
    protected override FileUploadPurpose Purpose
    {
        get
        {
#pragma warning disable OPENAI001 // FileUploadPurpose.UserData is experimental in OpenAI 2.10.
            return FileUploadPurpose.UserData;
#pragma warning restore OPENAI001
        }
    }
}
