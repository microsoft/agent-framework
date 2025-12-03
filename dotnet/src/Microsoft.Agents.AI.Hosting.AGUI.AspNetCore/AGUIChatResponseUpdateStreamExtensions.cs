// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal static class AGUIChatResponseUpdateStreamExtensions
{
    public static async IAsyncEnumerable<ChatResponseUpdate> FilterServerToolsFromMixedToolInvocationsAsync(
        this IAsyncEnumerable<ChatResponseUpdate> updates,
        List<AITool>? clientTools,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        if (clientTools is null || clientTools.Count == 0)
        {
            await foreach (var update in updates.WithCancellation(cancellationToken))
            {
                yield return update;
            }
            yield break;
        }

        var set = new HashSet<string>(clientTools.Count);
        foreach (var tool in clientTools)
        {
            set.Add(tool.Name);
        }

        await foreach (var update in updates.WithCancellation(cancellationToken))
        {
            if (update.FinishReason == ChatFinishReason.ToolCalls)
            {
                var containsClientTools = false;
                var containsServerTools = false;
                for (var i = update.Contents.Count - 1; i >= 0; i--)
                {
                    var content = update.Contents[i];
                    if (content is FunctionCallContent functionCallContent)
                    {
                        containsClientTools |= set.Contains(functionCallContent.Name);
                        containsServerTools |= !set.Contains(functionCallContent.Name);
                        if (containsClientTools && containsServerTools)
                        {
                            break;
                        }
                    }
                }

                if (containsClientTools && containsServerTools)
                {
                    var newContents = new List<AIContent>();
                    for (var i = update.Contents.Count - 1; i >= 0; i--)
                    {
                        var content = update.Contents[i];
                        if (content is not FunctionCallContent fcc ||
                            set.Contains(fcc.Name))
                        {
                            newContents.Add(content);
                        }
                    }

                    yield return new ChatResponseUpdate(update.Role, newContents)
                    {
                        ConversationId = update.ConversationId,
                        ResponseId = update.ResponseId,
                        FinishReason = update.FinishReason,
                        AdditionalProperties = update.AdditionalProperties,
                        AuthorName = update.AuthorName,
                        CreatedAt = update.CreatedAt,
                        MessageId = update.MessageId,
                        ModelId = update.ModelId
                    };
                }
                else
                {
                    yield return update;
                }
            }
            else
            {
                yield return update;
            }
        }
    }
}
