// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;

namespace Microsoft.Extensions.AI.Agents.OpenAI.ChatCompletion;

internal sealed class StreamingUpdatePipelineResponse : PipelineResponse
{
    /// <summary>
    /// Gets the HTTP status code. For streaming responses, this is typically 200.
    /// </summary>
    public override int Status => 200;

    /// <summary>
    /// Gets the reason phrase. For streaming responses, this is typically "OK".
    /// </summary>
    public override string ReasonPhrase => "OK";

    /// <summary>
    /// Streaming responses do not support direct content stream access.
    /// </summary>
    public override Stream? ContentStream
    {
        get => null;
        set { /* no-op */ }
    }

    /// <summary>
    /// Streaming responses do not support direct content access.
    /// </summary>
    public override BinaryData Content => BinaryData.FromString(string.Empty);

    /// <summary>
    /// Streaming responses do not have headers.
    /// </summary>
    protected override PipelineResponseHeaders HeadersCore => new EmptyPipelineResponseHeaders();

    /// <summary>
    /// Buffering content is not supported for streaming responses.
    /// </summary>
    public override BinaryData BufferContent(CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Buffering content is not supported for streaming responses.");

    /// <summary>
    /// Buffering content asynchronously is not supported for streaming responses.
    /// </summary>
    public override ValueTask<BinaryData> BufferContentAsync(CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Buffering content asynchronously is not supported for streaming responses.");

    /// <summary>
    /// Disposes resources. No resources to dispose for streaming response.
    /// </summary>
    public override void Dispose()
    {
        // No resources to dispose.
    }

    internal StreamingUpdatePipelineResponse(IAsyncEnumerable<AgentRunResponseUpdate> updates)
    {
    }

    private sealed class EmptyPipelineResponseHeaders : PipelineResponseHeaders
    {
        public override bool TryGetValue(string name, out string? value)
        {
            value = null;
            return false;
        }
        public override bool TryGetValues(string name, out IEnumerable<string>? values)
        {
            values = null;
            return false;
        }
        public override IEnumerator<KeyValuePair<string, string>> GetEnumerator()
        {
            yield break;
        }
    }
}
