// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// A truncating chat reducer that keeps the most recent messages up to a configured maximum,
/// preserving any leading system message. Removed messages are exposed via <see cref="RemovedMessages"/>
/// so that a caller can archive them (e.g. to a vector store).
/// </summary>
internal sealed class TruncatingChatReducer : IChatReducer
{
    private readonly int _maxMessages;

    /// <summary>
    /// Initializes a new instance of the <see cref="TruncatingChatReducer"/> class.
    /// </summary>
    /// <param name="maxMessages">The maximum number of non-system messages to retain.</param>
    public TruncatingChatReducer(int maxMessages)
    {
        this._maxMessages = maxMessages > 0 ? maxMessages : throw new ArgumentOutOfRangeException(nameof(maxMessages));
    }

    /// <summary>
    /// Gets the messages that were removed during the most recent call to <see cref="ReduceAsync"/>.
    /// </summary>
    public IReadOnlyList<ChatMessage> RemovedMessages { get; private set; } = [];

    /// <inheritdoc />
    public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = messages ?? throw new ArgumentNullException(nameof(messages));

        ChatMessage? systemMessage = null;
        Queue<ChatMessage> retained = new(capacity: this._maxMessages);
        List<ChatMessage> removed = [];

        foreach (var message in messages)
        {
            if (message.Role == ChatRole.System)
            {
                // Preserve the first system message outside the counting window.
                systemMessage ??= message;
            }
            else if (!message.Contents.Any(c => c is FunctionCallContent or FunctionResultContent))
            {
                if (retained.Count >= this._maxMessages)
                {
                    removed.Add(retained.Dequeue());
                }

                retained.Enqueue(message);
            }
        }

        this.RemovedMessages = removed;

        IEnumerable<ChatMessage> result = systemMessage is not null
            ? new[] { systemMessage }.Concat(retained)
            : retained;

        return Task.FromResult(result);
    }
}
