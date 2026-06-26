// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Tiny Server-Sent-Events frame parser for assertions.</summary>
internal static class Sse
{
    public static IReadOnlyList<(string Event, string Data)> Parse(string body)
    {
        var frames = new List<(string, string)>();
        foreach (var block in body.Replace("\r\n", "\n").Split("\n\n", StringSplitOptions.RemoveEmptyEntries))
        {
            string? evt = null;
            var data = new List<string>();
            foreach (var line in block.Split('\n'))
            {
                if (line.StartsWith("event:", StringComparison.Ordinal)) { evt = line["event:".Length..].Trim(); }
                else if (line.StartsWith("data:", StringComparison.Ordinal)) { data.Add(line["data:".Length..].Trim()); }
            }

            if (evt is not null)
            {
                frames.Add((evt, string.Join("\n", data)));
            }
        }

        return frames;
    }

    public static IEnumerable<string> Events(this IReadOnlyList<(string Event, string Data)> frames) => frames.Select(f => f.Event);
}
