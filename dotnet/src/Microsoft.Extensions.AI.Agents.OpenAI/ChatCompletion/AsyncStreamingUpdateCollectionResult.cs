// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using OpenAI.Chat;

namespace Microsoft.Extensions.AI.Agents.OpenAI.ChatCompletion;

internal sealed class AsyncStreamingUpdateCollectionResult : AsyncCollectionResult<StreamingChatCompletionUpdate>
{
    private readonly IAsyncEnumerable<AgentRunResponseUpdate> _updates;

    internal AsyncStreamingUpdateCollectionResult(IAsyncEnumerable<AgentRunResponseUpdate> updates)
    {
        this._updates = updates;
    }

    public override ContinuationToken? GetContinuationToken(ClientResult page) => null;

    public override IAsyncEnumerable<ClientResult> GetRawPagesAsync() =>
        AsyncEnumerable.Repeat(ClientResult.FromValue(this._updates, new StreamingUpdatePipelineResponse(this._updates)), 1);

    protected override async IAsyncEnumerable<StreamingChatCompletionUpdate> GetValuesFromPageAsync(ClientResult page)
    {
        var updates = ((ClientResult<IAsyncEnumerable<AgentRunResponseUpdate>>)page).Value;

        await foreach (var update in updates.ConfigureAwait(false))
        {
            yield return update.AsStreamingChatCompletionUpdate();
        }
    }
}
