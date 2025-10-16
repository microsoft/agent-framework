using System.Collections.Generic;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.ServerSentEvent;

/// <summary>
/// Represents a Server-Sent Events (SSE) frame.
/// </summary>
/// <param name="Id">The event ID.</param>
/// <param name="Name">The event name.</param>
/// <param name="Data">The event data.</param>
/// <param name="Comments">The event comments.</param>
public record SseFrame(
    string? Id = null,
    string? Name = null,
    IList<object>? Data = null,
    IList<string>? Comments = null)
{
    /// <summary>
    /// Creates a new SSE frame with the specified properties.
    /// </summary>
    /// <param name="id">The event ID.</param>
    /// <param name="name">The event name.</param>
    /// <param name="data">The event data.</param>
    /// <param name="comment">The event comment.</param>
    /// <returns>A new SSE frame.</returns>
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
