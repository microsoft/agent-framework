// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;

internal sealed class NeverCompactStrategy : ChatHistoryCompactionStrategy
{
    public NeverCompactStrategy()
        : base(new NoOpReducer())
    {
    }

    public override string Name => "NeverCompact";
    public override bool ShouldCompact(CompactionMetric metrics) => false;

    private sealed class NoOpReducer : IChatReducer
    {
        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
            => Task.FromResult(messages);
    }
}
