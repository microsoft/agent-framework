// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using ChatCompletionOptions = OpenAI.Chat.ChatCompletionOptions;
using CreateResponseOptions = OpenAI.Responses.CreateResponseOptions;
using IncludedResponseProperty = OpenAI.Responses.IncludedResponseProperty;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Keeps the service behind a hosted agent's chat client from storing the responses it produces, and
/// reports the deployment that ends up storing them anyway.
/// </summary>
/// <remarks>
/// <para>
/// A hosted turn is already recorded by the AgentServer SDK's storage provider, which runs around the
/// handler, and that record is the conversation the caller reads back. A service that also stores the
/// turn writes the same exchange a second time onto a trail of its own, which nothing here reads and
/// no one reconciles with the first.
/// </para>
/// <para>
/// Turning storage off is a container concern, so a deployment that still stores is a server-side
/// misconfiguration rather than a bad request, and is reported as such.
/// </para>
/// </remarks>
internal static class HostedStoredOutputCompatibility
{
    /// <summary>
    /// HTTP status returned when the agent's own service stored the turn. <c>501 Not Implemented</c>
    /// is a server-side classification, because the deployment, not the caller, is misconfigured; it is
    /// also non-retryable and distinct from the generic <c>500</c> so it stands out in telemetry.
    /// </summary>
    internal const int MisconfiguredAgentStatusCode = 501;

    /// <summary>
    /// Stable error code emitted in the response body so callers and tooling can match the condition.
    /// </summary>
    internal const string MisconfiguredAgentErrorCode = "agent_stored_output_not_disabled";

    /// <summary>
    /// Returns the error to throw when the agent's own service kept the turn.
    /// </summary>
    internal static ResponsesApiException CreateMisconfiguredAgentError() =>
        new(
            new Error(
                MisconfiguredAgentErrorCode,
                "The agent should not have server side storage enabled. This produced a new untracked conversation/response in the server while the hosted agent also generated a conversation for the request of the agent. This setting is only allowed when enabling the FoundryResponsesOptions.AllowStoredOutputEnabled flag, which leaves the agent's own storage setting untouched and keeps that second recording on purpose."),
            MisconfiguredAgentStatusCode);

    /// <summary>
    /// Installs a factory on <paramref name="options"/> that turns storage off on the request the agent's
    /// chat client is about to build.
    /// </summary>
    /// <param name="options">The chat options for this run.</param>
    /// <param name="agentRawRepresentationFactory">
    /// The factory the agent carries on its own <see cref="ChatOptions"/>, if any. It is invoked here and
    /// its result is what gets the setting, because <c>ChatClientAgent</c> chains the two by taking the
    /// agent's only when the request's returns null. A request factory that always answers would
    /// otherwise drop whatever the container configured.
    /// </param>
    /// <param name="includeReasoningEncryptedContent">
    /// Whether to ask for the encrypted form of the reasoning tokens, which is what keeps reasoning
    /// usable across turns while storage is off.
    /// </param>
    /// <remarks>
    /// Both OpenAI request shapes carry the setting, so a chat client speaking either protocol is
    /// covered. Anything else is a request type with no notion of storing a response, and is handed back
    /// untouched.
    /// </remarks>
    internal static void DisableStoredOutput(
        ChatOptions options,
        Func<IChatClient, object?>? agentRawRepresentationFactory,
        bool includeReasoningEncryptedContent)
    {
        options.RawRepresentationFactory = chatClient =>
        {
            switch (agentRawRepresentationFactory?.Invoke(chatClient))
            {
                case CreateResponseOptions responseOptions:
                    return DisableStoredOutput(responseOptions, includeReasoningEncryptedContent);

                case ChatCompletionOptions completionOptions:
                    completionOptions.StoredOutputEnabled = false;
                    return completionOptions;

                case { } configuredByTheAgent:
                    return configuredByTheAgent;

                default:
                    return DisableStoredOutput(new CreateResponseOptions(), includeReasoningEncryptedContent);
            }
        };
    }

    /// <summary>
    /// Reads whether a request the agent's chat client would send asks for the response to be stored.
    /// Returns <see langword="null"/> when the request shape carries no such setting, which is a request
    /// type this package has nothing to say about.
    /// </summary>
    internal static bool? ReadsAsStoringResponses(object? rawRepresentation) => rawRepresentation switch
    {
        CreateResponseOptions responseOptions => responseOptions.StoredOutputEnabled,
        ChatCompletionOptions completionOptions => completionOptions.StoredOutputEnabled,
        _ => null,
    };

    /// <summary>
    /// Turns storage off on a Responses request, and keeps reasoning usable across turns while it is off
    /// by asking for the encrypted form of the reasoning tokens. Mirrors what
    /// <c>AsIChatClientWithStoredOutputDisabled</c> does.
    /// </summary>
    private static CreateResponseOptions DisableStoredOutput(CreateResponseOptions responseOptions, bool includeReasoningEncryptedContent)
    {
        responseOptions.StoredOutputEnabled = false;

        if (includeReasoningEncryptedContent &&
            !responseOptions.IncludedProperties.Contains(IncludedResponseProperty.ReasoningEncryptedContent))
        {
            responseOptions.IncludedProperties.Add(IncludedResponseProperty.ReasoningEncryptedContent);
        }

        return responseOptions;
    }
}
