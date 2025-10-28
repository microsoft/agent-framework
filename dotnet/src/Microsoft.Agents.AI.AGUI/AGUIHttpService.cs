// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;

namespace Microsoft.Agents.AI.AGUI;

internal sealed class AGUIHttpService(HttpClient client, string endpoint)
{
    public async IAsyncEnumerable<BaseEvent> PostRunAsync(
        RunAgentInput input,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        using HttpResponseMessage response = await client.PostAsJsonAsync(
            endpoint,
            input,
            AGUIJsonSerializerContext.Default.RunAgentInput,
            cancellationToken).ConfigureAwait(false);

        response.EnsureSuccessStatusCode();

#if NET
        Stream responseStream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
#else
        Stream responseStream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
#endif
        var items = SseParser.Create(responseStream, ItemParser).EnumerateAsync(cancellationToken);
        await foreach (var sseItem in items.ConfigureAwait(false))
        {
            yield return sseItem.Data;
        }
    }

    private static BaseEvent ItemParser(string type, ReadOnlySpan<byte> data)
    {
        var result = JsonSerializer.Deserialize(data, AGUIJsonSerializerContext.Default.BaseEvent);
        if (result != null)
        {
            return result;
        }

        throw new InvalidOperationException("Failed to deserialize SSE item.");
    }
}
