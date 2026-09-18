// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>Allows everything and records every context it sees (point + deep clone).</summary>
internal sealed class AllowGuard : IInterceptor
{
    private readonly object _lock = new();

    public List<(string Point, JsonObject Context)> Seen { get; } = [];

    public List<string> Points
    {
        get { lock (this._lock) { return [.. this.Seen.Select(entry => entry.Point)]; } }
    }

    public JsonObject Context(string point)
    {
        lock (this._lock)
        {
            return this.Seen.First(entry => entry.Point == point).Context;
        }
    }

    public List<JsonObject> Contexts(string point)
    {
        lock (this._lock)
        {
            return [.. this.Seen.Where(entry => entry.Point == point).Select(entry => entry.Context)];
        }
    }

    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default)
    {
        lock (this._lock)
        {
            this.Seen.Add((context.InterceptionPoint.ToWireName(), (JsonObject)context.Json.DeepClone()));
        }

        return new(Verdict.Allow);
    }
}
