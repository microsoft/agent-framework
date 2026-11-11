// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// Configures a <see cref="DecisionChatEngine"/> for one provider.
/// </summary>
internal sealed class DecisionChatEngineOptions
{
    /// <summary>Gets the name of the decision model in messages, such as <c>Jev</c>.</summary>
    public required string ModelName { get; init; }

    /// <summary>
    /// Gets how the provider's questions are passed, which completes the sentence "it answers ..." in the message about
    /// unsupported chat options, such as <c>the questions passed with WithJevQuestions</c>.
    /// </summary>
    public required string QuestionsDescription { get; init; }

    /// <summary>Gets the prefix of the IDs of the function calls the engine returns, such as <c>typesafe</c>.</summary>
    public required string CallIdPrefix { get; init; }

    /// <summary>
    /// Gets the function that describes the answers to the caller's questions in the provider's own terms: the response
    /// text when no tool ran in the turn, and the raw representation of the response and its message.
    /// </summary>
    public required Func<DecisionResponse, DecisionChatAnswers> DescribeAnswers { get; init; }

    /// <summary>Gets the number of tool calls after which a turn answers the questions instead.</summary>
    public int MaximumToolCallsPerTurn { get; init; } = 1;

    /// <summary>Gets the logger that receives a warning for each tool that cannot be expressed as questions.</summary>
    public ILogger Logger { get; init; } = NullLogger.Instance;
}

/// <summary>
/// The answers to the caller's questions, described by the provider.
/// </summary>
/// <param name="Text">The response text when no tool ran in the turn.</param>
/// <param name="RawRepresentation">The raw representation of the response and its message.</param>
internal readonly record struct DecisionChatAnswers(string Text, object? RawRepresentation);
