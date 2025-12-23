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
        using HttpRequestMessage request = new(HttpMethod.Post, endpoint)
        {
            Content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput)
        };

        using HttpResponseMessage response = await client.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
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
        return JsonSerializer.Deserialize(data, AGUIJsonSerializerContext.Default.BaseEvent) ??
            throw new InvalidOperationException("Failed to deserialize SSE item.");
    }
}
