using System.Collections.Generic;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.ServerSentEvent;

public record SseFrame(
    string? Id = null,
    string? Name = null,
    IList<object>? Data = null,
    IList<string>? Comments = null)
{
    public static SseFrame Of(string? id = null, string? name = null, object? data = null, string? comment = null)
    {
        return new SseFrame
        {
            Id = id,
            Name = name,
            Data = data != null ? [data] : null,
            Comments = comment != null ? [comment] : null
        };
    }
}
