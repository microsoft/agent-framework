// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration.Transforms;

internal static class DefaultTransforms
{
    public static ValueTask<IEnumerable<ChatMessage>> FromInput<TInput>(TInput input, CancellationToken cancellationToken = default)
    {
#if !NETCOREAPP
        return new ValueTask<IEnumerable<ChatMessage>>(TransformInput());
#else
        return ValueTask.FromResult(TransformInput());
#endif

        IEnumerable<ChatMessage> TransformInput() =>
            input switch
            {
                IEnumerable<ChatMessage> messages => messages,
                ChatMessage message => [message],
                string text => [new ChatMessage(ChatRole.User, text)],
                _ => [new ChatMessage(ChatRole.User, JsonSerializer.Serialize(input))]
            };
    }

    public static ValueTask<TOutput> ToOutput<TOutput>(IList<ChatMessage> result, CancellationToken cancellationToken = default)
    {
        bool isSingleResult = result.Count == 1;

        TOutput output =
            GetDefaultOutput() ??
            GetObjectOutput() ??
            throw new InvalidOperationException($"Unable to transform output to {typeof(TOutput)}.");

        return new ValueTask<TOutput>(output);

        TOutput? GetObjectOutput()
        {
            if (!isSingleResult)
            {
                return default;
            }

            try
            {
                return JsonSerializer.Deserialize<TOutput>(result[0].Text);
            }
            catch (JsonException)
            {
                return default;
            }
        }

        TOutput? GetDefaultOutput()
        {
            object? output = null;
            if (typeof(TOutput).IsAssignableFrom(result.GetType()))
            {
                output = (object)result;
            }
            else if (isSingleResult && typeof(ChatMessage).IsAssignableFrom(typeof(TOutput)))
            {
                output = (object)result[0];
            }
            else if (isSingleResult && typeof(string) == typeof(TOutput))
            {
                output = result[0].Text ?? string.Empty;
            }

            return (TOutput?)output;
        }
    }
}
