// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Channels;
using System.Threading.Tasks;
using NAudio.Wave;

namespace RealtimeKeypoints.Audio;

/// <summary>
/// Captures raw PCM audio from the default microphone and exposes it as a channel of byte buffers.
/// </summary>
public sealed class MicrophoneAudioSource : IAsyncDisposable
{
    private readonly WaveInEvent _waveIn;
    private Channel<byte[]>? _channel;
    private bool _disposed;

    public MicrophoneAudioSource(int sampleRate = 16000, int bitsPerSample = 16, int channels = 1)
    {
        this._waveIn = new WaveInEvent
        {
            WaveFormat = new WaveFormat(sampleRate, bitsPerSample, channels),
            BufferMilliseconds = 100
        };
        this._waveIn.DataAvailable += this.OnDataAvailable;
        this._waveIn.RecordingStopped += this.OnRecordingStopped;
    }

    /// <summary>
    /// Starts recording from the microphone and returns a channel reader that yields audio buffers.
    /// </summary>
    public ChannelReader<byte[]> Start(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, typeof(MicrophoneAudioSource));

        if (this._channel is not null)
        {
            throw new InvalidOperationException("Microphone capture has already been started.");
        }

        var channel = Channel.CreateUnbounded<byte[]>(new UnboundedChannelOptions
        {
            SingleWriter = true,
            SingleReader = false
        });
        this._channel = channel;

        cancellationToken.Register(() => channel.Writer.TryComplete());

        this._waveIn.StartRecording();
        return channel.Reader;
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        if (this._channel is null)
        {
            return;
        }

        // Copy the recorded bytes because the buffer is reused by NAudio.
        var buffer = new byte[e.BytesRecorded];
        Array.Copy(e.Buffer, buffer, e.BytesRecorded);

        // Drop frames if the reader is closed.
        if (!this._channel.Writer.TryWrite(buffer))
        {
            // If the reader is gone, stop recording to free the microphone handle.
            this._waveIn.StopRecording();
        }
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        this._channel?.Writer.TryComplete(e.Exception);
    }

    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;

        if (this._channel is not null)
        {
            this._channel.Writer.TryComplete();
        }

        await Task.Run(() =>
        {
            try
            {
                this._waveIn.StopRecording();
            }
            catch
            {
                // Ignore failures during shutdown.
            }
        }).ConfigureAwait(false);

        this._waveIn.DataAvailable -= this.OnDataAvailable;
        this._waveIn.RecordingStopped -= this.OnRecordingStopped;
        this._waveIn.Dispose();
    }
}
