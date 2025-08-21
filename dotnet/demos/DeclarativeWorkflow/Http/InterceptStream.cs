// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;

namespace DeclarativeWorkflow;

internal sealed class InterceptStream(Stream source, Action<byte[], int, int> callback) : Stream
{
    public override bool CanRead => source.CanRead;

    public override bool CanSeek => source.CanSeek;

    public override bool CanWrite => source.CanWrite;

    public override long Length => source.Length;

    public override long Position { get => source.Position; set => source.Position = value; }

    public override void Flush() => source.Flush();

    public override int Read(byte[] buffer, int offset, int count)
    {
        int actual = source.Read(buffer, offset, count);

        callback.Invoke(buffer, offset, actual);

        return actual;
    }

    public override long Seek(long offset, SeekOrigin origin) => source.Seek(offset, origin);

    public override void SetLength(long value) => source.SetLength(value);

    public override void Write(byte[] buffer, int offset, int count) => source.Write(buffer, offset, count);
}
