// Copyright (c) Microsoft. All rights reserved.

using System.Buffers;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;

namespace RealtimeKeypoints.Realtime;

/// <summary>
/// Minimal WebSocket client for Azure OpenAI GPT-Realtime audio sessions.
/// </summary>
public sealed class AzureRealtimeClient : IAsyncDisposable
{
    private const string ApiVersion = "2024-10-01-preview";
    private static readonly string[] s_textOnlyModalities = ["text"];
    private readonly Uri _endpoint;
    private readonly string _deploymentName;
    private readonly string _apiKey;
    private readonly SemaphoreSlim _connectLock = new(1, 1);
    private ClientWebSocket? _socket;
    private bool _disposed;

    public AzureRealtimeClient(Uri endpoint, string deploymentName, string apiKey)
    {
        this._endpoint = endpoint ?? throw new ArgumentNullException(nameof(endpoint));
        this._deploymentName = deploymentName ?? throw new ArgumentNullException(nameof(deploymentName));
        this._apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
    }

    /// <summary>
    /// Streams transcript segments produced by Azure OpenAI from the supplied PCM audio channel.
    /// </summary>
    public async IAsyncEnumerable<RealtimeTranscriptSegment> StreamTranscriptsAsync(
        ChannelReader<byte[]> audioReader,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(this._disposed, typeof(AzureRealtimeClient));
        if (audioReader is null)
        {
            throw new ArgumentNullException(nameof(audioReader));
        }

        await this.EnsureConnectedAsync(cancellationToken).ConfigureAwait(false);
        ClientWebSocket socket = this._socket!;

        var transcriptChannel = Channel.CreateUnbounded<RealtimeTranscriptSegment>(new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = true
        });

        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var sendTask = Task.Run(() => this.SendAudioAsync(audioReader, socket, linkedCts.Token), linkedCts.Token);
        var receiveTask = Task.Run(() => this.ReceiveResponsesAsync(socket, transcriptChannel.Writer, linkedCts.Token), linkedCts.Token);

        try
        {
            await foreach (var segment in transcriptChannel.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
            {
                yield return segment;
            }
        }
        finally
        {
            linkedCts.Cancel();
            transcriptChannel.Writer.TryComplete();
            try
            {
                await Task.WhenAll(sendTask, receiveTask).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                // Expected when cancelling the linked CTS during shutdown.
            }
        }
    }

    private async Task SendAudioAsync(ChannelReader<byte[]> audioReader, ClientWebSocket socket, CancellationToken cancellationToken)
    {
        // With server VAD and input_audio_transcription enabled, the server will:
        // 1. Detect speech automatically.
        // 2. Generate transcription when speech ends.
        // 3. Send conversation.item.input_audio_transcription.completed events.
        // We just need to stream audio continuously!

        while (await audioReader.WaitToReadAsync(cancellationToken).ConfigureAwait(false))
        {
            while (audioReader.TryRead(out var buffer))
            {
                await SendJsonAsync(socket, new
                {
                    type = "input_audio_buffer.append",
                    audio = Convert.ToBase64String(buffer)
                }, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async Task ReceiveResponsesAsync(ClientWebSocket socket, ChannelWriter<RealtimeTranscriptSegment> writer, CancellationToken cancellationToken)
    {
        byte[] buffer = ArrayPool<byte>.Shared.Rent(32 * 1024);
        var segment = new ArraySegment<byte>(buffer);
        using var messageBuffer = new MemoryStream();

        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                var result = await socket.ReceiveAsync(segment, cancellationToken).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    break;
                }

                messageBuffer.Write(buffer, 0, result.Count);
                if (!result.EndOfMessage)
                {
                    continue;
                }

                string payload = Encoding.UTF8.GetString(messageBuffer.GetBuffer(), 0, (int)messageBuffer.Length);
                messageBuffer.SetLength(0);
                await this.ProcessMessageAsync(payload, writer, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException)
        {
            // Expected when cancellation is requested.
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
            writer.TryComplete();
        }
    }

    private async Task ProcessMessageAsync(string payload, ChannelWriter<RealtimeTranscriptSegment> writer, CancellationToken cancellationToken)
    {
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement root = document.RootElement;

        if (!root.TryGetProperty("type", out var typeProperty))
        {
            return;
        }

        string? type = typeProperty.GetString();
        if (type is null)
        {
            return;
        }

        switch (type)
        {
            case "conversation.item.input_audio_transcription.completed":
                // This event contains the actual transcription of user's speech!
                if (root.TryGetProperty("transcript", out var transcriptElement))
                {
                    string? transcript = transcriptElement.GetString();
                    if (!string.IsNullOrWhiteSpace(transcript))
                    {
                        await writer.WriteAsync(new RealtimeTranscriptSegment(transcript, DateTimeOffset.UtcNow, IsFinal: true), cancellationToken).ConfigureAwait(false);
                    }
                }
                break;

            case "conversation.item.input_audio_transcription.failed":
                // Transcription failed
                if (root.TryGetProperty("error", out var transcriptError))
                {
                    string? errorMsg = null;
                    if (transcriptError.TryGetProperty("message", out var messageElement))
                    {
                        errorMsg = messageElement.GetString();
                    }
                    Console.WriteLine($"[WARNING] Audio transcription failed: {errorMsg ?? "Unknown error"}");
                }
                break;

            case "error":
                if (root.TryGetProperty("error", out var errorElement))
                {
                    string? message = null;
                    if (errorElement.TryGetProperty("message", out var messageElement))
                    {
                        message = messageElement.GetString();
                    }
                    Console.WriteLine($"[WARNING] Azure OpenAI realtime error: {message ?? "Unknown error"}");
                }
                break;
        }
    }

    private async Task EnsureConnectedAsync(CancellationToken cancellationToken)
    {
        if (this._socket is { State: WebSocketState.Open })
        {
            return;
        }

        await this._connectLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._socket is { State: WebSocketState.Open })
            {
                return;
            }

            this._socket?.Dispose();
            var socket = new ClientWebSocket();
            socket.Options.SetRequestHeader("api-key", this._apiKey);
            socket.Options.SetRequestHeader("OpenAI-Beta", "realtime=v1");
            socket.Options.AddSubProtocol("realtime");

            Uri uri = this.BuildRealtimeUri();
            await socket.ConnectAsync(uri, cancellationToken).ConfigureAwait(false);

            await SendJsonAsync(socket, new
            {
                type = "session.update",
                session = new
                {
                    modalities = s_textOnlyModalities,
                    input_audio_format = "pcm16",
                    input_audio_transcription = new
                    {
                        model = "whisper-1"
                    },
                    turn_detection = new
                    {
                        type = "server_vad",
                        threshold = 0.5,
                        prefix_padding_ms = 300,
                        silence_duration_ms = 500
                    }
                }
            }, cancellationToken).ConfigureAwait(false);

            this._socket = socket;
        }
        finally
        {
            this._connectLock.Release();
        }
    }

    private Uri BuildRealtimeUri()
    {
        var builder = new UriBuilder(this._endpoint);

        // Convert HTTP(S) scheme to WebSocket scheme
        if (string.Equals(builder.Scheme, "https", StringComparison.OrdinalIgnoreCase))
        {
            builder.Scheme = "wss";
        }
        else if (string.Equals(builder.Scheme, "http", StringComparison.OrdinalIgnoreCase))
        {
            builder.Scheme = "ws";
        }

        string path = builder.Path;
        if (!path.EndsWith('/'))
        {
            path += "/";
        }

        builder.Path = path + "openai/realtime";

        var parameters = new List<string>();
        if (!string.IsNullOrEmpty(builder.Query))
        {
            parameters.Add(builder.Query.TrimStart('?'));
        }

        parameters.Add($"api-version={ApiVersion}");
        // Preview API versions use 'deployment' parameter
        parameters.Add($"deployment={Uri.EscapeDataString(this._deploymentName)}");
        builder.Query = string.Join('&', parameters);
        return builder.Uri;
    }

    private static Task SendJsonAsync(ClientWebSocket socket, object payload, CancellationToken cancellationToken)
    {
        string json = JsonSerializer.Serialize(payload);
        byte[] bytes = Encoding.UTF8.GetBytes(json);
        return socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, cancellationToken);
    }

    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        this._connectLock.Dispose();

        if (this._socket is ClientWebSocket socket)
        {
            try
            {
                if (socket.State == WebSocketState.Open)
                {
                    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "disposing", CancellationToken.None).ConfigureAwait(false);
                }
            }
            catch
            {
                // ignore disposal errors
            }
            finally
            {
                socket.Dispose();
            }
        }
    }
}
