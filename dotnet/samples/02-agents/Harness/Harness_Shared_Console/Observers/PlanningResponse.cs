// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Represents a structured response from the agent while in planning mode.
/// Used with structured output to enable consistent rendering of clarification
/// questions and approval requests in the console.
/// </summary>
public class PlanningResponse
{
    /// <summary>
    /// Gets or sets the type of planning response.
    /// </summary>
    [JsonPropertyName("type")]
    public required PlanningResponseType Type { get; set; }

    /// <summary>
    /// Gets or sets the list of questions or items to present to the user.
    /// For clarification, this contains one or more questions (each with choices).
    /// For approval, this contains exactly one item with the plan summary.
    /// </summary>
    [JsonPropertyName("questions")]
    [Description("For clarifications, this has one or more questions to ask the user (each with choices). For approvals, this has exactly one item containing the plan summary for the user to approve.")]
    public required List<PlanningQuestion> Questions { get; set; }
}

/// <summary>
/// Represents a single question or item within a <see cref="PlanningResponse"/>.
/// </summary>
public class PlanningQuestion
{
    /// <summary>
    /// Gets or sets the message to display to the user.
    /// For clarification, this is the question. For approval, this is the plan summary.
    /// </summary>
    [JsonPropertyName("message")]
    [Description("For clarifications, this has the question that needs to be clarified with the user. For approvals, this would contain a summary of the execution plan that the user needs to approve.")]
    public required string Message { get; set; }

    /// <summary>
    /// Gets or sets the list of choices for the user to pick from.
    /// Only used for clarification questions. Null when no predefined choices are offered.
    /// </summary>
    [JsonPropertyName("choices")]
    [Description("""
        For clarifications, this has a list of options that the user can choose from.
        null for approvals.
        
        Note: for clarifications, the user will always also be presented with a free form input option, so make sure that each choice provided here is a valid input for the next turn.
        E.g. if the question is "Which stock are you referring to?" then valid choices might be ["AAPL", "MSFT", "GOOG"], and the user could also type their own answer.
        Invalid choices would be ["Enter tickers directly", "Paste tickers"], since these conflict with the already existing freeform option, and don't directly provide valid inputs for the next turn.
    """)]
    public List<string>? Choices { get; set; }
}
