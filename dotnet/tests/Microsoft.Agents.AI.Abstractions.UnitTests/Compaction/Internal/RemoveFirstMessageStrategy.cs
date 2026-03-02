// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;

internal sealed class RemoveFirstMessageStrategy : ChatHistoryCompactionStrategy
{
    public RemoveFirstMessageStrategy()
        : base(new RemoveFirstReducer())
    {
    }

    public override string Name => "RemoveFirst";

    public override bool ShouldCompact(CompactionMetric metrics) => metrics.MessageCount > 0;

    private sealed class RemoveFirstReducer : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
        {
            List<ChatMessage> list = messages.ToList();
            if (list.Count > 1)
            {
                list.RemoveAt(0);
            }

            return Task.FromResult<IEnumerable<ChatMessage>>(list);
        }
    }
}
