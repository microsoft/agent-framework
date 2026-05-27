// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI.Abstractions;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Parent-side bridge for subprocess Python execution with JSON-lines IPC and host-tool dispatch.
/// </summary>
internal sealed class ProcessBridge
{
    private readonly Dictionary<string, AIFunction> _tools;
    private readonly ProcessExecutionLimits _limits;
    private readonly IReadOnlyDictionary<string, string> _environment;
    private readonly string? _workingDirectory;
    private readonly string _pythonExecutable;
    private readonly string? _runnerScript;

    public ProcessBridge(
        IEnumerable<AIFunction> tools,
        ProcessExecutionLimits limits,
        IReadOnlyDictionary<string, string> environment,
        string? workingDirectory,
        string pythonExecutable,
        string? runnerScript)
    {
        _tools = tools.ToDictionary(t => t.Metadata.Name, t => t);
        _limits = limits;
        _environment = environment;
        _workingDirectory = workingDirectory;
        _pythonExecutable = pythonExecutable;
        _runnerScript = runnerScript;
    }

    /// <summary>
    /// Runs generated Python code in a child process with timeout and tool call handling.
    /// </summary>
    public async Task<Dictionary<string, object?>> RunAsync(string code, CancellationToken cancellationToken = default)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = _pythonExecutable,
            Arguments = _runnerScript == null ? "-I -m agent_framework_local_codeact._runner" : $"-I \"{_runnerScript}\"",
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = _workingDirectory,
        };

        // Set environment variables
        startInfo.Environment.Clear();
        foreach (var (key, value) in _environment)
        {
            startInfo.Environment[key] = value;
        }

        // Add Windows-specific environment variables if needed
        if (OperatingSystem.IsWindows())
        {
            foreach (var key in new[] { "SYSTEMROOT", "COMSPEC", "PATHEXT" })
            {
                var value = Environment.GetEnvironmentVariable(key);
                if (value != null && !startInfo.Environment.ContainsKey(key))
                {
                    startInfo.Environment[key] = value;
                }
            }
        }

        using var process = Process.Start(startInfo) ?? throw new InvalidOperationException("Failed to start Python process.");

        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(TimeSpan.FromSeconds(_limits.TimeoutSeconds));

            return await CommunicateAsync(process, code, cts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            // Timeout from our CTS
            await StopProcessAsync(process).ConfigureAwait(false);
            throw new TimeoutException($"Generated code exceeded {_limits.TimeoutSeconds} seconds.");
        }
        catch
        {
            await StopProcessAsync(process).ConfigureAwait(false);
            throw;
        }
    }

    private async Task<Dictionary<string, object?>> CommunicateAsync(
        Process process,
        string code,
        CancellationToken cancellationToken)
    {
        // Send initial request to child process
        var request = new Dictionary<string, object?>
        {
            ["code"] = code,
            ["tool_names"] = _tools.Keys.ToList(),
            ["max_stdout_bytes"] = _limits.MaxStdoutBytes,
            ["max_stderr_bytes"] = _limits.MaxStderrBytes,
        };

        var requestJson = JsonSerializer.Serialize(request, new JsonSerializerOptions { WriteIndented = false });
        await process.StandardInput.WriteLineAsync(requestJson.AsMemory(), cancellationToken).ConfigureAwait(false);
        await process.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);

        // Process messages from child
        while (true)
        {
            var line = await process.StandardOutput.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line == null)
            {
                var stderr = await ReadStderrAsync(process, cancellationToken).ConfigureAwait(false);
                throw new InvalidOperationException($"Local CodeAct subprocess exited without a result. stderr: {stderr}");
            }

            Dictionary<string, object?>? message;
            try
            {
                message = JsonSerializer.Deserialize<Dictionary<string, object?>>(line);
            }
            catch (JsonException ex)
            {
                throw new InvalidOperationException($"Failed to parse JSON from subprocess: {line}", ex);
            }

            if (message == null)
            {
                continue;
            }

            var messageType = message.TryGetValue("type", out var typeValue) ? typeValue?.ToString() : null;

            if (messageType == "complete")
            {
                // Execution complete
                if (!message.TryGetValue("result", out var resultObj))
                {
                    throw new InvalidOperationException("Complete message missing 'result' field.");
                }

                var result = resultObj as Dictionary<string, object?> ?? new Dictionary<string, object?>();
                CheckResultSize(result);
                return result;
            }

            if (messageType == "error")
            {
                var details = message.TryGetValue("traceback", out var tb) ? tb?.ToString() :
                             message.TryGetValue("message", out var msg) ? msg?.ToString() : "Unknown execution error.";
                await StopProcessAsync(process).ConfigureAwait(false);
                throw new InvalidOperationException(details);
            }

            if (messageType == "tool_call")
            {
                // Handle tool call
                await HandleToolCallAsync(process, message, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async Task HandleToolCallAsync(
        Process process,
        Dictionary<string, object?> message,
        CancellationToken cancellationToken)
    {
        var callId = message.TryGetValue("call_id", out var cid) ? Convert.ToInt32(cid) : 0;
        var name = message.TryGetValue("name", out var n) ? n?.ToString() : null;
        var kwargsObj = message.TryGetValue("kwargs", out var kw) ? kw : null;

        if (string.IsNullOrEmpty(name))
        {
            await SendToolResponseAsync(process, callId, false, null, "MissingToolName", "Tool call missing 'name'.", cancellationToken).ConfigureAwait(false);
            return;
        }

        if (!_tools.TryGetValue(name, out var tool))
        {
            await SendToolResponseAsync(process, callId, false, null, "UnknownTool", $"Unknown tool: {name}", cancellationToken).ConfigureAwait(false);
            return;
        }

        try
        {
            // Convert kwargs to JSON element for tool invocation
            var kwargsJson = JsonSerializer.Serialize(kwargsObj);
            var kwargsElement = JsonSerializer.Deserialize<JsonElement>(kwargsJson);

            // Invoke the tool
            var result = await tool.InvokeAsync(kwargsElement, cancellationToken).ConfigureAwait(false);
            var safeResult = MakeJsonSafe(result);

            await SendToolResponseAsync(process, callId, true, safeResult, null, null, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await SendToolResponseAsync(process, callId, false, null, ex.GetType().Name, ex.Message, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task SendToolResponseAsync(
        Process process,
        int callId,
        bool ok,
        object? result,
        string? excType,
        string? message,
        CancellationToken cancellationToken)
    {
        var response = new Dictionary<string, object?>
        {
            ["call_id"] = callId,
            ["ok"] = ok,
        };

        if (ok)
        {
            response["result"] = result;
        }
        else
        {
            response["exc_type"] = excType;
            response["message"] = message;
        }

        var responseJson = JsonSerializer.Serialize(response, new JsonSerializerOptions { WriteIndented = false });
        await process.StandardInput.WriteLineAsync(responseJson.AsMemory(), cancellationToken).ConfigureAwait(false);
        await process.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    private async Task<string> ReadStderrAsync(Process process, CancellationToken cancellationToken)
    {
        var stderr = new StringBuilder();
        var buffer = new char[4096];
        int bytesRead = 0;
        int totalBytes = 0;

        while (totalBytes < _limits.MaxStderrBytes &&
               (bytesRead = await process.StandardError.ReadAsync(buffer, cancellationToken).ConfigureAwait(false)) > 0)
        {
            stderr.Append(buffer, 0, Math.Min(bytesRead, _limits.MaxStderrBytes - totalBytes));
            totalBytes += bytesRead;
        }

        return stderr.ToString();
    }

    private static async Task StopProcessAsync(Process process)
    {
        try
        {
            process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync().ConfigureAwait(false);
        }
        catch
        {
            // Ignore errors during cleanup
        }
    }

    private void CheckResultSize(Dictionary<string, object?> result)
    {
        var encoded = JsonSerializer.SerializeToUtf8Bytes(result, new JsonSerializerOptions { WriteIndented = false });
        if (encoded.Length > _limits.MaxStdoutBytes) // Reusing MaxStdoutBytes as max result bytes
        {
            throw new InvalidOperationException("Generated code result exceeded max size.");
        }
    }

    private static object? MakeJsonSafe(object? value)
    {
        if (value == null)
        {
            return null;
        }

        try
        {
            // Test if it's JSON-serializable
            _ = JsonSerializer.Serialize(value);
            return value;
        }
        catch
        {
            // Convert to string representation if not serializable
            return value.ToString();
        }
    }
}
