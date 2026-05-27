// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Validates Python code using the embedded Python AST validator.
/// </summary>
internal sealed class CodeValidator
{
    private readonly string _pythonExecutable;
    private readonly string? _validatorScript;
    private readonly string[]? _allowedImports;
    private readonly string[]? _blockedImports;
    private readonly string[]? _allowedBuiltins;
    private readonly string[]? _blockedBuiltins;

    public CodeValidator(
        string pythonExecutable,
        string? validatorScript = null,
        string[]? allowedImports = null,
        string[]? blockedImports = null,
        string[]? allowedBuiltins = null,
        string[]? blockedBuiltins = null)
    {
        _pythonExecutable = pythonExecutable;
        _validatorScript = validatorScript;
        _allowedImports = allowedImports;
        _blockedImports = blockedImports;
        _allowedBuiltins = allowedBuiltins;
        _blockedBuiltins = blockedBuiltins;
    }

    /// <summary>
    /// Validates Python code against AST allow-lists.
    /// </summary>
    /// <param name="code">The Python code to validate.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <exception cref="CodeValidationException">Thrown if validation fails.</exception>
    public async Task ValidateAsync(string code, CancellationToken cancellationToken = default)
    {
        // Extract embedded validator script to temp file if not provided
        string validatorPath = _validatorScript ?? await ExtractValidatorScriptAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            // Build validation request
            var request = new Dictionary<string, object?>
            {
                ["code"] = code,
            };

            if (_allowedImports != null)
            {
                request["allowed_imports"] = _allowedImports;
            }

            if (_blockedImports != null)
            {
                request["blocked_imports"] = _blockedImports;
            }

            if (_allowedBuiltins != null)
            {
                request["allowed_builtins"] = _allowedBuiltins;
            }

            if (_blockedBuiltins != null)
            {
                request["blocked_builtins"] = _blockedBuiltins;
            }

            var requestJson = JsonSerializer.Serialize(request);

            // Run validator
            var startInfo = new ProcessStartInfo
            {
                FileName = _pythonExecutable,
                Arguments = $"-I \"{validatorPath}\"",
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };

            using var process = Process.Start(startInfo) ?? throw new InvalidOperationException("Failed to start Python validator.");

            await process.StandardInput.WriteLineAsync(requestJson.AsMemory(), cancellationToken).ConfigureAwait(false);
            await process.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);
            process.StandardInput.Close();

            var output = await process.StandardOutput.ReadToEndAsync(cancellationToken).ConfigureAwait(false);
            var stderr = await process.StandardError.ReadToEndAsync(cancellationToken).ConfigureAwait(false);

            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);

            if (process.ExitCode != 0)
            {
                // Validation failed
                var response = JsonSerializer.Deserialize<Dictionary<string, object?>>(output);
                var errors = response?.TryGetValue("errors", out var e) == true ? e?.ToString() : output;
                throw new CodeValidationException($"Code validation failed: {errors}");
            }
        }
        finally
        {
            // Clean up temp validator script if we created it
            if (_validatorScript == null && File.Exists(validatorPath))
            {
                try
                {
                    File.Delete(validatorPath);
                }
                catch
                {
                    // Ignore cleanup errors
                }
            }
        }
    }

    private static async Task<string> ExtractValidatorScriptAsync(CancellationToken cancellationToken)
    {
        var assembly = Assembly.GetExecutingAssembly();
        var resourceName = "Microsoft.Agents.AI.LocalCodeAct.Resources.validator.py";

        await using var stream = assembly.GetManifestResourceStream(resourceName)
            ?? throw new InvalidOperationException($"Embedded resource '{resourceName}' not found.");

        var tempPath = Path.Combine(Path.GetTempPath(), $"validator_{Guid.NewGuid():N}.py");

        await using var fileStream = File.Create(tempPath);
        await stream.CopyToAsync(fileStream, cancellationToken).ConfigureAwait(false);

        return tempPath;
    }
}

/// <summary>
/// Exception thrown when Python code validation fails.
/// </summary>
public sealed class CodeValidationException : Exception
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CodeValidationException"/> class.
    /// </summary>
    public CodeValidationException(string message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CodeValidationException"/> class.
    /// </summary>
    public CodeValidationException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
