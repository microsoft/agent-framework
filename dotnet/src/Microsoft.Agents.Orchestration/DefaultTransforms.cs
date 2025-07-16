// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

internal static class DefaultTransforms
{
    public static ValueTask<IEnumerable<ChatMessage>> FromInput<TInput>(TInput input, JsonSerializerOptions? serializerOptions = null, CancellationToken cancellationToken = default)
    {
        serializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;
        return new(input switch
        {
            IEnumerable<ChatMessage> messages => messages,
            ChatMessage message => [message],
            string text => [new ChatMessage(ChatRole.User, text)],
            _ => [new ChatMessage(ChatRole.User, JsonSerializer.Serialize(input, serializerOptions.GetTypeInfo(typeof(TInput))))]
        });
    }

    public static ValueTask<TOutput> ToOutput<TOutput>(IList<ChatMessage> result, JsonSerializerOptions? serializerOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(result);

        serializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;
        bool isSingleResult = result.Count == 1;

        if (result is TOutput)
        {
            return new((TOutput)(object)result);
        }

        if (isSingleResult)
        {
            if (typeof(ChatMessage).IsAssignableFrom(typeof(TOutput)))
            {
                return new((TOutput)(object)result[0]);
            }

            if (typeof(string) == typeof(TOutput))
            {
                return new((TOutput)(object)(result[0].Text ?? string.Empty));
            }

            try
            {
                return new((TOutput)JsonSerializer.Deserialize(result[0].Text, serializerOptions.GetTypeInfo(typeof(TOutput)))!);
            }
            catch (JsonException)
            {
            }
        }

        throw new InvalidOperationException($"Unable to transform output to {typeof(TOutput)}.");
    }
}
