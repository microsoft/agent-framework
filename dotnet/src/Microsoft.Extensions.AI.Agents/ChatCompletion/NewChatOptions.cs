// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Contains new properties that will be added to <see cref="ChatOptions"/> in the future.
/// </summary>
/// <remarks>
/// This class contains temporary properties to support new options
/// that are not part of the official <see cref="ChatOptions"/> class yet.
/// Later, these properties will be moved to the official <see cref="ChatOptions"/> class
/// and this class will be removed. Therefore, please expect a breaking change
/// if you are using this class directly in your code.
/// </remarks>
public class NewChatOptions : ChatOptions
{
    /// <summary>
    /// Specifies whether the chat client should await the long-running execution result.
    /// </summary>
    public bool? AwaitRunResult { get; set; }

    /// <summary>
    /// Specifies the identifier of an update within a conversation to start generating chat responses after.
    /// </summary>
    public string? StartAfter { get; set; }

    /// <summary>
    /// Specifies identifier of the previous response in a conversation.
    /// </summary>
    public string? PreviousResponseId { get; set; }

    /// <inheritdoc/>
    public override ChatOptions Clone()
    {
        NewChatOptions options = new()
        {
            AdditionalProperties = this.AdditionalProperties?.Clone(),
            AllowMultipleToolCalls = this.AllowMultipleToolCalls,
            ConversationId = this.ConversationId,
            FrequencyPenalty = this.FrequencyPenalty,
            Instructions = this.Instructions,
            MaxOutputTokens = this.MaxOutputTokens,
            ModelId = this.ModelId,
            PresencePenalty = this.PresencePenalty,
            RawRepresentationFactory = this.RawRepresentationFactory,
            ResponseFormat = this.ResponseFormat,
            Seed = this.Seed,
            Temperature = this.Temperature,
            ToolMode = this.ToolMode,
            TopK = this.TopK,
            TopP = this.TopP,
        };

        if (this.StopSequences is not null)
        {
            options.StopSequences = new List<string>(this.StopSequences);
        }

        if (this.Tools is not null)
        {
            options.Tools = new List<AITool>(this.Tools);
        }

        // The following property is specific to the NewChatOptions
        options.AwaitRunResult = this.AwaitRunResult;
        options.StartAfter = this.StartAfter;
        options.PreviousResponseId = this.PreviousResponseId;

        return options;
    }
}
