// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using LogLevel = Microsoft.Extensions.Logging.LogLevel;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating AI agent that logs agent operations to an <see cref="ILogger"/>.
/// </summary>
/// <remarks>
/// <para>
/// The provided implementation of <see cref="AIAgent"/> is thread-safe for concurrent use so long as the
/// <see cref="ILogger"/> employed is also thread-safe for concurrent use.
/// </para>
/// <para>
/// When the employed <see cref="ILogger"/> enables <see cref="LogLevel.Trace"/>, the contents of
/// messages, options, and responses are logged. These may contain sensitive application data.
/// <see cref="LogLevel.Trace"/> is disabled by default and should never be enabled in a production environment.
/// Messages and options are not logged at other logging levels.
/// </para>
/// </remarks>
public sealed partial class LoggingAgent : DelegatingAIAgent
{
    /// <summary>An <see cref="ILogger"/> instance used for all logging.</summary>
    private readonly ILogger _logger;

    /// <summary>The <see cref="JsonSerializerOptions"/> to use for serialization of state written to the logger.</summary>
    private JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>Initializes a new instance of the <see cref="LoggingAgent"/> class.</summary>
    /// <param name="innerAgent">The underlying <see cref="AIAgent"/>.</param>
    /// <param name="logger">An <see cref="ILogger"/> instance that will be used for all logging.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> or <paramref name="logger"/> is <see langword="null"/>.</exception>
    public LoggingAgent(AIAgent innerAgent, ILogger logger)
        : base(innerAgent)
    {
        this._logger = Throw.IfNull(logger);
        this._jsonSerializerOptions = AgentJsonUtilities.DefaultOptions;
    }

    /// <summary>Gets or sets JSON serialization options to use when serializing logging data.</summary>
    public JsonSerializerOptions JsonSerializerOptions
    {
        get => this._jsonSerializerOptions;
        set => this._jsonSerializerOptions = Throw.IfNull(value);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (this._logger.IsEnabled(LogLevel.Debug))
        {
            if (this._logger.IsEnabled(LogLevel.Trace))
            {
                this.LogInvokedSensitive(nameof(RunAsync), this.AsJson(messages), this.AsJson(options), this.AsJson(this.GetService<AIAgentMetadata>()));
            }
            else
            {
                this.LogInvoked(nameof(RunAsync));
            }
        }

        try
        {
            AgentRunResponse response = await base.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

            if (this._logger.IsEnabled(LogLevel.Debug))
            {
                if (this._logger.IsEnabled(LogLevel.Trace))
                {
                    this.LogCompletedSensitive(nameof(RunAsync), this.AsJson(response));
                }
                else
                {
                    this.LogCompleted(nameof(RunAsync));
                }
            }

            return response;
        }
        catch (OperationCanceledException)
        {
            this.LogInvocationCanceled(nameof(RunAsync));
            throw;
        }
        catch (Exception ex)
        {
            this.LogInvocationFailed(nameof(RunAsync), ex);
            throw;
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._logger.IsEnabled(LogLevel.Debug))
        {
            if (this._logger.IsEnabled(LogLevel.Trace))
            {
                this.LogInvokedSensitive(nameof(RunStreamingAsync), this.AsJson(messages), this.AsJson(options), this.AsJson(this.GetService<AIAgentMetadata>()));
            }
            else
            {
                this.LogInvoked(nameof(RunStreamingAsync));
            }
        }

        IAsyncEnumerator<AgentRunResponseUpdate> e;
        try
        {
            e = base.RunStreamingAsync(messages, thread, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            this.LogInvocationCanceled(nameof(RunStreamingAsync));
            throw;
        }
        catch (Exception ex)
        {
            this.LogInvocationFailed(nameof(RunStreamingAsync), ex);
            throw;
        }

        try
        {
            AgentRunResponseUpdate? update = null;
            while (true)
            {
                try
                {
                    if (!await e.MoveNextAsync().ConfigureAwait(false))
                    {
                        break;
                    }

                    update = e.Current;
                }
                catch (OperationCanceledException)
                {
                    this.LogInvocationCanceled(nameof(RunStreamingAsync));
                    throw;
                }
                catch (Exception ex)
                {
                    this.LogInvocationFailed(nameof(RunStreamingAsync), ex);
                    throw;
                }

                if (this._logger.IsEnabled(LogLevel.Trace))
                {
                    this.LogStreamingUpdateSensitive(this.AsJson(update));
                }

                yield return update;
            }

            this.LogCompleted(nameof(RunStreamingAsync));
        }
        finally
        {
            await e.DisposeAsync().ConfigureAwait(false);
        }
    }

    private string AsJson<T>(T value)
    {
        try
        {
            return JsonSerializer.Serialize(value, this._jsonSerializerOptions.GetTypeInfo(typeof(T)));
        }
        catch
        {
            // If serialization fails, return a simple string representation
            return value?.ToString() ?? "null";
        }
    }

    [LoggerMessage(LogLevel.Debug, "{MethodName} invoked.")]
    private partial void LogInvoked(string methodName);

    [LoggerMessage(LogLevel.Trace, "{MethodName} invoked: {Messages}. Options: {Options}. Metadata: {Metadata}.")]
    private partial void LogInvokedSensitive(string methodName, string messages, string options, string metadata);

    [LoggerMessage(LogLevel.Debug, "{MethodName} completed.")]
    private partial void LogCompleted(string methodName);

    [LoggerMessage(LogLevel.Trace, "{MethodName} completed: {Response}.")]
    private partial void LogCompletedSensitive(string methodName, string response);

    [LoggerMessage(LogLevel.Trace, "RunStreamingAsync received update: {Update}")]
    private partial void LogStreamingUpdateSensitive(string update);

    [LoggerMessage(LogLevel.Debug, "{MethodName} canceled.")]
    private partial void LogInvocationCanceled(string methodName);

    [LoggerMessage(LogLevel.Error, "{MethodName} failed.")]
    private partial void LogInvocationFailed(string methodName, Exception error);
}
