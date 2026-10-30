// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace SampleApp;

internal sealed class StatelessWebSearchChatClient(IChatClient innerClient) : DelegatingChatClient(innerClient)
{
    public override Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default) =>
        base.GetResponseAsync(FilterSearchResults(messages), options, cancellationToken);

    public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default) =>
        base.GetStreamingResponseAsync(FilterSearchResults(messages), options, cancellationToken);

    private static List<ChatMessage> FilterSearchResults(IEnumerable<ChatMessage> messages)
    {
        List<ChatMessage> result = [];
        foreach (ChatMessage message in messages)
        {
            if (message.Role != ChatRole.Assistant ||
                !message.Contents.Any(static content => content is WebSearchToolResultContent { RawRepresentation: WebSearchCallResponseItem }))
            {
                result.Add(message);
                continue;
            }

            // In this sample, Foundry returned invalid_payload when the OpenAI adapter sent
            // this raw web_search_call again after a local tool call with store=false.
            // The public OpenAI API accepted that pattern. Copy the message so only the next
            // model request omits the raw result; keep the original session history, cited
            // text, and local tool calls unchanged.
            ChatMessage filtered = message.Clone();
            filtered.Contents = message.Contents
                .Where(static content => content is not WebSearchToolResultContent { RawRepresentation: WebSearchCallResponseItem })
                .ToList();
            result.Add(filtered);
        }

        return result;
    }
}
