// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Parent-side IPC bridge that launches the Python runner, sends a single execution request,
/// services tool calls, and returns the final execution result.
/// </summary>
internal sealed class ProcessBridge
{
    private static readonly JsonSerializerOptions s_jsonOptions = new()
    {
        WriteIndented = false,
    };

    private readonly string _pythonExecutable;
    private readonly string _runnerScript;
    private readonly IReadOnlyDictionary<string, AIFunction> _tools;
    private readonly ProcessExecutionLimits _limits;
    private readonly IReadOnlyDictionary<string, string>? _environment;
    private readonly string? _workingDirectory;

    public ProcessBridge(
        string pythonExecutable,
        string runnerScript,
        IReadOnlyList<AIFunction> tools,
        ProcessExecutionLimits limits,
        IReadOnlyDictionary<string, string>? environment,
        string? workingDirectory)
    {
        this._pythonExecutable = pythonExecutable;
        this._runnerScript = runnerScript;
        this._tools = tools.ToDictionary(t => t.Name, StringComparer.Ordinal);
        this._limits = limits;
        this._environment = environment;
        this._workingDirectory = workingDirectory;
    }

    /// <summary>Represents the parsed final result returned by the Python runner.</summary>
    public sealed class ExecutionResult
    {
        public string Stdout { get; init; } = string.Empty;
        public string Stderr { get; init; } = string.Empty;
        public bool OutputPresent { get; init; }
        public JsonElement? Output { get; init; }
        public bool StdoutTruncated { get; init; }
        public bool StderrTruncated { get; init; }
    }

    public async Task<ExecutionResult> RunAsync(string code, CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = this._pythonExecutable,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        startInfo.ArgumentList.Add("-I");
        startInfo.ArgumentList.Add(this._runnerScript);

        if (!string.IsNullOrEmpty(this._workingDirectory))
        {
            startInfo.WorkingDirectory = this._workingDirectory;
        }

        this.ConfigureEnvironment(startInfo);

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Failed to start Python runner process.");

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(TimeSpan.FromSeconds(this._limits.TimeoutSeconds));

        var stderrTask = ReadCappedAsync(process.StandardError, this._limits.MaxStderrBytes, timeoutCts.Token);

        try
        {
            return await this.CommunicateAsync(process, code, stderrTask, timeoutCts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            TryKill(process);
            throw new TimeoutException($"Generated code exceeded {this._limits.TimeoutSeconds} seconds.");
        }
        catch
        {
            TryKill(process);
            throw;
        }
    }

    private void ConfigureEnvironment(ProcessStartInfo startInfo)
    {
        // Null => inherit the parent environment (documented contract on
        // LocalCodeActProviderOptions.Environment). Callers wanting a scrubbed
        // environment pass an empty dictionary.
        if (this._environment is null)
        {
            return;
        }

        startInfo.Environment.Clear();
        foreach (var kvp in this._environment)
        {
            startInfo.Environment[kvp.Key] = kvp.Value;
        }

        // Without these on Windows, Python may fail to load its standard library.
        if (OperatingSystem.IsWindows())
        {
            foreach (var key in new[] { "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "TEMP", "TMP" })
            {
                if (!startInfo.Environment.ContainsKey(key))
                {
                    var existing = Environment.GetEnvironmentVariable(key);
                    if (!string.IsNullOrEmpty(existing))
                    {
                        startInfo.Environment[key] = existing;
                    }
                }
            }
        }
    }

    private async Task<ExecutionResult> CommunicateAsync(
        Process process,
        string code,
        Task<(string Text, bool Truncated)> stderrTask,
        CancellationToken cancellationToken)
    {
        var request = new JsonObject
        {
            ["code"] = code,
            ["tool_names"] = new JsonArray(this._tools.Keys.Select(k => (JsonNode?)JsonValue.Create(k)).ToArray()),
            ["max_stdout_bytes"] = this._limits.MaxStdoutBytes,
            ["max_stderr_bytes"] = this._limits.MaxStderrBytes,
        };

        await process.StandardInput.WriteLineAsync(request.ToJsonString(s_jsonOptions).AsMemory(), cancellationToken).ConfigureAwait(false);
        await process.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var line = await process.StandardOutput.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
            {
                var stderr = await stderrTask.ConfigureAwait(false);
                throw new InvalidOperationException(
                    $"Local CodeAct subprocess exited without a result. stderr: {stderr.Text}");
            }

            JsonObject message;
            try
            {
                message = JsonNode.Parse(line) as JsonObject
                    ?? throw new InvalidOperationException("Subprocess produced a non-object JSON message.");
            }
            catch (JsonException ex)
            {
                throw new InvalidOperationException($"Failed to parse JSON message from subprocess: {line}", ex);
            }

            switch ((string?)message["type"])
            {
                case "complete":
                    return this.ParseComplete(message);

                case "error":
                    var excType = (string?)message["exc_type"] ?? "Error";
                    var msg = (string?)message["message"] ?? "Unknown subprocess error.";
                    var tb = (string?)message["traceback"];
                    throw new InvalidOperationException(
                        string.IsNullOrEmpty(tb) ? $"{excType}: {msg}" : $"{excType}: {msg}\n{tb}");

                case "tool_call":
                    await this.HandleToolCallAsync(process, message, cancellationToken).ConfigureAwait(false);
                    break;

                default:
                    // Unknown message types are ignored to remain forward compatible.
                    break;
            }
        }
    }

    private ExecutionResult ParseComplete(JsonObject message)
    {
        var result = message["result"] as JsonObject ?? new JsonObject();

        var json = result.ToJsonString();
        if (Encoding.UTF8.GetByteCount(json) > this._limits.MaxResultBytes)
        {
            throw new InvalidOperationException(
                $"Generated code result exceeded the configured max of {this._limits.MaxResultBytes} bytes.");
        }

        JsonElement? output = null;
        if (result["output"] is JsonNode outputNode)
        {
            output = JsonDocument.Parse(outputNode.ToJsonString()).RootElement.Clone();
        }

        return new ExecutionResult
        {
            Stdout = (string?)result["stdout"] ?? string.Empty,
            Stderr = (string?)result["stderr"] ?? string.Empty,
            OutputPresent = (bool?)result["output_present"] ?? false,
            Output = output,
            StdoutTruncated = (bool?)result["stdout_truncated"] ?? false,
            StderrTruncated = (bool?)result["stderr_truncated"] ?? false,
        };
    }

    private async Task HandleToolCallAsync(Process process, JsonObject message, CancellationToken cancellationToken)
    {
        // call_id is Python's id(kwargs) which can be a 64-bit value on 64-bit Python.
        long callId = 0;
        if (message["call_id"] is JsonValue cidValue && cidValue.TryGetValue<long>(out var parsedId))
        {
            callId = parsedId;
        }

        var name = (string?)message["name"];
        if (string.IsNullOrEmpty(name))
        {
            await SendToolResponseAsync(process, callId, ok: false, result: null,
                excType: "ToolError", excMessage: "Tool call missing 'name'.", cancellationToken).ConfigureAwait(false);
            return;
        }

        if (!this._tools.TryGetValue(name!, out var tool))
        {
            await SendToolResponseAsync(process, callId, ok: false, result: null,
                excType: "UnknownTool", excMessage: $"Unknown tool: {name}", cancellationToken).ConfigureAwait(false);
            return;
        }

        var kwargs = message["kwargs"] as JsonObject ?? new JsonObject();
        var arguments = new AIFunctionArguments();
        foreach (var (key, value) in kwargs)
        {
            arguments[key] = value;
        }

        try
        {
            var result = await tool.InvokeAsync(arguments, cancellationToken).ConfigureAwait(false);
            await SendToolResponseAsync(process, callId, ok: true, result, excType: null, excMessage: null, cancellationToken).ConfigureAwait(false);
        }
#pragma warning disable CA1031
        catch (Exception ex)
#pragma warning restore CA1031
        {
            await SendToolResponseAsync(process, callId, ok: false, result: null,
                excType: ex.GetType().Name, excMessage: ex.Message, cancellationToken).ConfigureAwait(false);
        }
    }

    private static async Task SendToolResponseAsync(
        Process process,
        long callId,
        bool ok,
        object? result,
        string? excType,
        string? excMessage,
        CancellationToken cancellationToken)
    {
        var response = new JsonObject
        {
            ["call_id"] = callId,
            ["ok"] = ok,
        };

        if (ok)
        {
            response["result"] = SerializeResult(result);
        }
        else
        {
            response["exc_type"] = excType;
            response["message"] = excMessage;
        }

        await process.StandardInput.WriteLineAsync(response.ToJsonString(s_jsonOptions).AsMemory(), cancellationToken).ConfigureAwait(false);
        await process.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    private static JsonNode? SerializeResult(object? value)
    {
        if (value is null)
        {
            return null;
        }

        if (value is JsonNode node)
        {
            return node;
        }

        try
        {
            var typeInfo = AIJsonUtilities.DefaultOptions.GetTypeInfo(value.GetType());
            var json = JsonSerializer.Serialize(value, typeInfo);
            return JsonNode.Parse(json);
        }
#pragma warning disable CA1031
        catch
#pragma warning restore CA1031
        {
            return JsonValue.Create(value.ToString());
        }
    }

    private static async Task<(string Text, bool Truncated)> ReadCappedAsync(StreamReader reader, int maxBytes, CancellationToken cancellationToken)
    {
        var sb = new StringBuilder();
        var buffer = new char[4096];
        var truncated = false;
        var totalBytes = 0;

        try
        {
            while (true)
            {
                var read = await reader.ReadAsync(buffer.AsMemory(), cancellationToken).ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }

                var chunk = new string(buffer, 0, read);
                var chunkBytes = Encoding.UTF8.GetByteCount(chunk);
                if (totalBytes + chunkBytes > maxBytes)
                {
                    var remaining = Math.Max(0, maxBytes - totalBytes);
                    if (remaining > 0)
                    {
                        sb.Append(chunk[..Math.Min(chunk.Length, remaining)]);
                    }

                    truncated = true;
                    break;
                }

                sb.Append(chunk);
                totalBytes += chunkBytes;
            }
        }
        catch (OperationCanceledException)
        {
            // Allow caller to propagate the timeout exception.
        }
#pragma warning disable CA1031
        catch
#pragma warning restore CA1031
        {
            // Best effort: return what we have so far.
        }

        return (sb.ToString(), truncated);
    }

    private static void TryKill(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
#pragma warning disable CA1031
        catch
#pragma warning restore CA1031
        {
            // best-effort
        }
    }
}
