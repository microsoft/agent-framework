// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.OpenAI;

internal sealed class AsyncStreamingResponseUpdateCollectionResult : AsyncCollectionResult<StreamingResponseUpdate>
{
    private readonly IAsyncEnumerable<AgentRunResponseUpdate> _updates;

    internal AsyncStreamingResponseUpdateCollectionResult(IAsyncEnumerable<AgentRunResponseUpdate> updates)
    {
        this._updates = updates;
    }

    public override ContinuationToken? GetContinuationToken(ClientResult page) => null;

    public override async IAsyncEnumerable<ClientResult> GetRawPagesAsync()
    {
        yield return ClientResult.FromValue(this._updates, new StreamingUpdatePipelineResponse(this._updates));
    }

    protected async override IAsyncEnumerable<StreamingResponseUpdate> GetValuesFromPageAsync(ClientResult page)
    {
        var updates = ((ClientResult<IAsyncEnumerable<AgentRunResponseUpdate>>)page).Value;

        await foreach (var update in updates.ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case StreamingResponseUpdate rawUpdate:
                    yield return rawUpdate;
                    break;

                case Extensions.AI.ChatResponseUpdate { RawRepresentation: StreamingResponseUpdate rawUpdate }:
                    yield return rawUpdate;
                    break;

                default:
                    // TODO: The OpenAI library does not currently expose model factory methods for creating
                    // StreamingResponseUpdates. We are thus unable to manufacture such instances when there isn't
                    // already one in the update and instead skip them.
                    break;
            }
        }
    }
}
