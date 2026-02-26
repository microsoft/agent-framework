// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.OpenAI;

internal sealed class AsyncStreamingChatCompletionUpdateCollectionResult : AsyncCollectionResult<StreamingChatCompletionUpdate>
{
    private readonly IAsyncEnumerable<AgentResponseUpdate> _updates;

    internal AsyncStreamingChatCompletionUpdateCollectionResult(IAsyncEnumerable<AgentResponseUpdate> updates)
    {
        this._updates = updates;
    }

    public override ContinuationToken? GetContinuationToken(ClientResult page) => null;

    public override async IAsyncEnumerable<ClientResult> GetRawPagesAsync()
    {
        yield return ClientResult.FromValue(this._updates, new StreamingUpdatePipelineResponse(this._updates));
    }

    protected override IAsyncEnumerable<StreamingChatCompletionUpdate> GetValuesFromPageAsync(ClientResult page)
    {
        var updates = ((ClientResult<IAsyncEnumerable<AgentResponseUpdate>>)page).Value;

        return updates.AsChatResponseUpdatesAsync().AsOpenAIStreamingChatCompletionUpdatesAsync();
    }
}
