// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console;

/// <summary>
/// Represents an action returned by an observer at the end of an agent turn.
/// Subtypes describe either a question to ask the user (<see cref="FollowUpQuestion"/>)
/// or a message to add directly to the next agent input (<see cref="FollowUpMessage"/>).
/// </summary>
public abstract record FollowUpAction;

/// <summary>
/// Represents a question that should be presented to the user. The
/// <see cref="Continuation"/> delegate is invoked with the user's answer and the
/// UX state driver, and returns an optional <see cref="ChatMessage"/> to add to the
/// next agent invocation.
/// </summary>
/// <param name="Prompt">The question text shown to the user.</param>
/// <param name="Continuation">
/// Invoked with the user's answer and the UX state driver. The driver lets the
/// continuation write output (e.g., an action label like "Approved") in addition
/// to producing an optional <see cref="ChatMessage"/> for the next agent invocation.
/// </param>
public abstract record FollowUpQuestion(
    string Prompt,
    Func<string, IUXStateDriver, Task<ChatMessage?>> Continuation) : FollowUpAction;

/// <summary>
/// A free-form text question. The user may type any response.
/// </summary>
/// <param name="Prompt">The question text shown to the user.</param>
/// <param name="Continuation">Continuation that builds the response message.</param>
public sealed record TextFollowUpQuestion(
    string Prompt,
    Func<string, IUXStateDriver, Task<ChatMessage?>> Continuation)
    : FollowUpQuestion(Prompt, Continuation);

/// <summary>
/// A choice question. The user picks from <paramref name="Choices"/>, optionally with
/// the ability to enter custom text when <paramref name="AllowCustomText"/> is true.
/// </summary>
/// <param name="Prompt">The question text shown to the user.</param>
/// <param name="Choices">The list of pre-defined choices.</param>
/// <param name="AllowCustomText">If true, the user may type a custom response in addition to the listed choices.</param>
/// <param name="Continuation">Continuation that builds the response message.</param>
public sealed record ChoiceFollowUpQuestion(
    string Prompt,
    IReadOnlyList<string> Choices,
    bool AllowCustomText,
    Func<string, IUXStateDriver, Task<ChatMessage?>> Continuation)
    : FollowUpQuestion(Prompt, Continuation);

/// <summary>
/// A message to add directly to the next agent invocation without prompting the user.
/// </summary>
/// <param name="Message">The chat message to add.</param>
public sealed record FollowUpMessage(ChatMessage Message) : FollowUpAction;
