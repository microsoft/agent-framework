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

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Runs the embedded Python AST validator in a child process with a strict timeout.
/// </summary>
internal sealed class CodeValidator
{
    private readonly string _pythonExecutable;
    private readonly string _validatorScript;
    private readonly TimeSpan _timeout;
    private readonly IReadOnlyList<string>? _allowedImports;
    private readonly IReadOnlyList<string>? _blockedImports;
    private readonly IReadOnlyList<string>? _allowedBuiltins;
    private readonly IReadOnlyList<string>? _blockedBuiltins;

    public CodeValidator(
        string pythonExecutable,
        string validatorScript,
        TimeSpan timeout,
        IReadOnlyList<string>? allowedImports,
        IReadOnlyList<string>? blockedImports,
        IReadOnlyList<string>? allowedBuiltins,
        IReadOnlyList<string>? blockedBuiltins)
    {
        this._pythonExecutable = pythonExecutable;
        this._validatorScript = validatorScript;
        this._timeout = timeout;
        this._allowedImports = allowedImports;
        this._blockedImports = blockedImports;
        this._allowedBuiltins = allowedBuiltins;
        this._blockedBuiltins = blockedBuiltins;
    }

    /// <summary>Validates Python source code against the configured allow-lists.</summary>
    /// <exception cref="CodeValidationException">Thrown when validation fails.</exception>
    public async Task ValidateAsync(string code, CancellationToken cancellationToken)
    {
        var request = new JsonObject
        {
            ["code"] = code,
        };

        AddList(request, "allowed_imports", this._allowedImports);
        AddList(request, "blocked_imports", this._blockedImports);
        AddList(request, "allowed_builtins", this._allowedBuiltins);
        AddList(request, "blocked_builtins", this._blockedBuiltins);

        var requestJson = request.ToJsonString();

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
        startInfo.ArgumentList.Add(this._validatorScript);

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Failed to start Python validator process.");

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(this._timeout);

        try
        {
            await process.StandardInput.WriteLineAsync(requestJson.AsMemory(), timeoutCts.Token).ConfigureAwait(false);
            await process.StandardInput.FlushAsync(timeoutCts.Token).ConfigureAwait(false);
            process.StandardInput.Close();

            var stdoutTask = process.StandardOutput.ReadToEndAsync(timeoutCts.Token);
            var stderrTask = process.StandardError.ReadToEndAsync(timeoutCts.Token);

            await process.WaitForExitAsync(timeoutCts.Token).ConfigureAwait(false);

            var stdout = await stdoutTask.ConfigureAwait(false);
            _ = await stderrTask.ConfigureAwait(false);

            if (process.ExitCode == 0)
            {
                return;
            }

            throw new CodeValidationException(ExtractError(stdout));
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            TryKill(process);
            throw new CodeValidationException($"Code validation exceeded {this._timeout.TotalSeconds:F0} seconds.");
        }
        catch
        {
            TryKill(process);
            throw;
        }
    }

    private static string ExtractError(string output)
    {
        if (string.IsNullOrWhiteSpace(output))
        {
            return "Code validation failed.";
        }

        try
        {
            using var doc = JsonDocument.Parse(output);
            if (doc.RootElement.TryGetProperty("errors", out var errors) && errors.ValueKind == JsonValueKind.Array)
            {
                var sb = new StringBuilder();
                foreach (var err in errors.EnumerateArray())
                {
                    if (sb.Length > 0)
                    {
                        sb.Append("; ");
                    }

                    sb.Append(err.ValueKind == JsonValueKind.String ? err.GetString() : err.ToString());
                }

                return sb.Length > 0 ? sb.ToString() : output;
            }

            if (doc.RootElement.TryGetProperty("message", out var message) && message.ValueKind == JsonValueKind.String)
            {
                return message.GetString() ?? output;
            }
        }
        catch (JsonException)
        {
            // fall through
        }

        return output;
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
        catch
        {
#pragma warning disable CA1031 // Do not catch general exception types
            // best-effort cleanup
#pragma warning restore CA1031
        }
    }

    private static void AddList(JsonObject obj, string key, IReadOnlyList<string>? values)
    {
        if (values is null)
        {
            return;
        }

        obj[key] = new JsonArray(values.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray());
    }
}
