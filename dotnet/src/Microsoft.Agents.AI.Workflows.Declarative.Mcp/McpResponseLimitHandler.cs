// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Bounds decoded response data before the MCP transport buffers or parses it.
/// </summary>
internal sealed class McpResponseLimitHandler(HttpMessageHandler innerHandler, int maxResponseBodyBytes, int maxSseEventBytes) : HttpMessageHandler
{
    private readonly HttpMessageInvoker _inner = new(innerHandler, disposeHandler: false);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        HttpResponseMessage response = await this._inner.SendAsync(request, cancellationToken).ConfigureAwait(false);
        try
        {
            bool isEventStream = response.IsSuccessStatusCode && string.Equals(
                response.Content.Headers.ContentType?.MediaType, "text/event-stream", StringComparison.OrdinalIgnoreCase);
            int limit = isEventStream ? maxSseEventBytes : maxResponseBodyBytes;
            if (!isEventStream && response.Content.Headers.ContentLength > limit)
            {
                throw new HttpRequestException("The MCP response body exceeds the configured byte limit.");
            }

            response.Content = new LimitedContent(response.Content, limit, isEventStream);
            return response;
        }
        catch
        {
            response.Dispose();
            throw;
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._inner.Dispose();
        }

        base.Dispose(disposing);
    }

    private sealed class LimitedContent : HttpContent
    {
        private readonly HttpContent _inner;
        private readonly int _limit;
        private readonly bool _isEventStream;

        public LimitedContent(HttpContent inner, int limit, bool isEventStream)
        {
            this._inner = inner;
            this._limit = limit;
            this._isEventStream = isEventStream;
            foreach (KeyValuePair<string, IEnumerable<string>> header in inner.Headers)
            {
                this.Headers.TryAddWithoutValidation(header.Key, header.Value);
            }
        }

        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }

        protected override Task<Stream> CreateContentReadStreamAsync() =>
            this.GetLimitedStreamAsync(CancellationToken.None);

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) =>
            this.CopyToCoreAsync(stream, CancellationToken.None);

#if NET
        protected override Task<Stream> CreateContentReadStreamAsync(CancellationToken cancellationToken) =>
            this.GetLimitedStreamAsync(cancellationToken);

        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context, CancellationToken cancellationToken) =>
            this.CopyToCoreAsync(stream, cancellationToken);
#endif

        private async Task<Stream> GetLimitedStreamAsync(CancellationToken cancellationToken)
        {
#if NET
            Stream stream = await this._inner.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
#else
            cancellationToken.ThrowIfCancellationRequested();
            Stream stream = await this._inner.ReadAsStreamAsync().ConfigureAwait(false);
#endif
            return new LimitedReadStream(stream, this._limit, this._isEventStream);
        }

        private async Task CopyToCoreAsync(Stream destination, CancellationToken cancellationToken)
        {
            using Stream source = await this.GetLimitedStreamAsync(cancellationToken).ConfigureAwait(false);
            await source.CopyToAsync(destination, 81920, cancellationToken).ConfigureAwait(false);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this._inner.Dispose();
            }

            base.Dispose(disposing);
        }
    }

    internal sealed class LimitedReadStream(Stream inner, int limit, bool isEventStream) : Stream
    {
        private long _bytesRead;
        private bool _lineHasContent;
        private bool _previousWasCarriageReturn;
        private bool _resetAfterCarriageReturn;

        public override bool CanRead => inner.CanRead;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position
        {
            get => throw new NotSupportedException();
            set => throw new NotSupportedException();
        }

        public override int Read(byte[] buffer, int offset, int count)
        {
            int read = inner.Read(buffer, offset, this.GetReadCount(count));
            this.ValidateBytes(buffer.AsSpan(offset, read));
            return read;
        }

#if NET
        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken) =>
            this.ReadAsync(buffer.AsMemory(offset, count), cancellationToken).AsTask();

        public override int Read(Span<byte> buffer)
        {
            int read = inner.Read(buffer.Slice(0, this.GetReadCount(buffer.Length)));
            this.ValidateBytes(buffer.Slice(0, read));
            return read;
        }

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            int read = await inner.ReadAsync(buffer.Slice(0, this.GetReadCount(buffer.Length)), cancellationToken).ConfigureAwait(false);
            this.ValidateBytes(buffer.Span.Slice(0, read));
            return read;
        }
#else
        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            int read = await inner.ReadAsync(buffer, offset, this.GetReadCount(count), cancellationToken).ConfigureAwait(false);
            this.ValidateBytes(buffer.AsSpan(offset, read));
            return read;
        }
#endif

        private int GetReadCount(int count) =>
            (int)Math.Min(count, Math.Min(81920L, isEventStream ? (long)limit + 1 : limit - this._bytesRead + 1));

        private void ValidateBytes(ReadOnlySpan<byte> buffer)
        {
            if (!isEventStream)
            {
                this._bytesRead += buffer.Length;
                this.ThrowIfLimitExceeded();
                return;
            }

            for (int i = 0; i < buffer.Length; i++)
            {
                byte value = buffer[i];
                if (this._previousWasCarriageReturn)
                {
                    // A CRLF delimiter can straddle reads; count its LF without starting another line.
                    this._previousWasCarriageReturn = false;
                    if (value == '\n')
                    {
                        this._bytesRead++;
                        this.ThrowIfLimitExceeded();
                        if (this._resetAfterCarriageReturn)
                        {
                            this._bytesRead = 0;
                            this._resetAfterCarriageReturn = false;
                        }

                        continue;
                    }

                    if (this._resetAfterCarriageReturn)
                    {
                        this._bytesRead = 0;
                        this._resetAfterCarriageReturn = false;
                    }
                }

                this._bytesRead++;
                this.ThrowIfLimitExceeded();
                if (value is (byte)'\r' or (byte)'\n')
                {
                    this._previousWasCarriageReturn = value == '\r';
                    if (!this._lineHasContent)
                    {
                        if (this._previousWasCarriageReturn)
                        {
                            this._resetAfterCarriageReturn = true;
                        }
                        else
                        {
                            this._bytesRead = 0;
                        }
                    }

                    this._lineHasContent = false;
                }
                else
                {
                    this._lineHasContent = true;
                }
            }
        }

        private void ThrowIfLimitExceeded()
        {
            if (this._bytesRead > limit)
            {
                throw new HttpRequestException(isEventStream
                    ? "The MCP SSE event exceeds the configured byte limit."
                    : "The MCP response body exceeds the configured byte limit.");
            }
        }

        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                inner.Dispose();
            }

            base.Dispose(disposing);
        }
    }
}
