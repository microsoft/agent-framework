// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using AdaptiveCards;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace M365Agent.Agents;

/// <summary>
/// An <see cref="AIContent"/> type allows an <see cref="AIAgent"/> to return adaptive cards as part of its response messages.
/// </summary>
internal sealed class AdaptiveCardAIContent : AIContent
{
    public AdaptiveCardAIContent(AdaptiveCard adaptiveCard)
    {
        this.AdaptiveCard = adaptiveCard ?? throw new ArgumentNullException(nameof(adaptiveCard));
    }

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
    [JsonConstructor]
    public AdaptiveCardAIContent(string adaptiveCardJson)
    {
        this.AdaptiveCardJson = adaptiveCardJson;
    }
#pragma warning restore CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

    [JsonIgnore]
    public AdaptiveCard AdaptiveCard { get; private set; }

    public string AdaptiveCardJson
    {
        get => this.AdaptiveCard.ToJson();
        set => this.AdaptiveCard = AdaptiveCard.FromJson(value).Card;
    }
}
