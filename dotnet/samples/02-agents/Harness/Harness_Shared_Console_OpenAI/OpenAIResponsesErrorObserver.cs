// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.

using Harness.Shared.Console.Observers;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Harness.Shared.Console.OpenAI;

/// <summary>
/// Detects and displays error/incomplete status from OpenAI Responses API streaming updates.
/// Handles <see cref="StreamingResponseFailedUpdate"/> and <see cref="StreamingResponseIncompleteUpdate"/>
/// which are not surfaced as <see cref="ErrorContent"/> by the chat client.
/// </summary>
/// <remarks>
/// Note: <see cref="StreamingResponseErrorUpdate"/> is already handled by the SDK — it produces
/// an <see cref="ErrorContent"/> which is displayed by <see cref="ErrorDisplayObserver"/>.
/// This observer covers the cases where the SDK does not produce <see cref="ErrorContent"/>.
/// </remarks>
public sealed class OpenAIResponsesErrorObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnResponseUpdateAsync(IUXStateDriver ux, AgentResponseUpdate update, AIAgent agent, AgentSession session)
    {
        // AgentResponseUpdate.RawRepresentation is the ChatResponseUpdate,
        // whose RawRepresentation is the underlying StreamingResponseUpdate.
        object? rawUpdate = (update.RawRepresentation as ChatResponseUpdate)?.RawRepresentation
            ?? update.RawRepresentation;

        switch (rawUpdate)
        {
            case StreamingResponseFailedUpdate failedUpdate:
                // Only display if the response has error details populated.
                // When error is null, a follow-up StreamingResponseErrorUpdate typically
                // carries the real error — the SDK surfaces that as ErrorContent,
                // which is displayed by ErrorDisplayObserver.
                if (failedUpdate.Response?.Error is { } error)
                {
                    string errorMessage = error.Message ?? "Unknown error";
                    string? errorCode = error.Code.ToString();
                    string errorText = $"❌ Response failed: {errorMessage}";
                    if (!string.IsNullOrEmpty(errorCode))
                    {
                        errorText += $" (code: {errorCode})";
                    }

                    await ux.WriteInfoLineAsync(errorText, ConsoleColor.Red);
                }

                break;

            case StreamingResponseIncompleteUpdate incompleteUpdate:
                string? reason = incompleteUpdate.Response?.IncompleteStatusDetails?.Reason?.ToString();
                string incompleteText = $"⚠️ Response incomplete: {reason ?? "unknown reason"}";
                await ux.WriteInfoLineAsync(incompleteText, ConsoleColor.Yellow);
                break;
        }
    }
}
