// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.LocalCodeAct.Internal;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class ProcessBridgeTests
{
    [Fact]
    public async Task ReadCappedAsync_ExactUtf8Limit_ReturnsFullTextAsync()
    {
        var result = await ReadCappedAsync("A😀B", maxBytes: 6);

        Assert.Equal("A😀B", result.Text);
        Assert.False(result.Truncated);
    }

    [Fact]
    public async Task ReadCappedAsync_TruncatesAtRuneBoundaryAsync()
    {
        var result = await ReadCappedAsync("A😀B", maxBytes: 5);

        Assert.Equal("A😀", result.Text);
        Assert.True(result.Truncated);
        Assert.Equal(5, Encoding.UTF8.GetByteCount(result.Text));
    }

    [Fact]
    public async Task ReadCappedAsync_DoesNotSplitSurrogatePairWhenRuneDoesNotFitAsync()
    {
        var result = await ReadCappedAsync("A😀B", maxBytes: 2);

        Assert.Equal("A", result.Text);
        Assert.True(result.Truncated);
        Assert.Equal(1, Encoding.UTF8.GetByteCount(result.Text));
    }

    private static async Task<(string Text, bool Truncated)> ReadCappedAsync(string text, int maxBytes)
    {
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(text));
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: false, bufferSize: 1024, leaveOpen: false);
        return await ProcessBridge.ReadCappedAsync(reader, maxBytes, CancellationToken.None);
    }
}
