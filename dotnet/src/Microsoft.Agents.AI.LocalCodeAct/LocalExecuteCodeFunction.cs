// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Standalone <c>execute_code</c> <see cref="AIFunction"/> that runs Python code locally.
/// </summary>
/// <remarks>
/// This function executes LLM-generated Python code in a subprocess. It is intended for
/// environments that already provide process, filesystem, and network isolation (e.g.,
/// Azure Container Instances, VMs, Foundry hosted agents). It is NOT a security sandbox.
/// </remarks>
public sealed class LocalExecuteCodeFunction : AIFunction, IDisposable
{
    private const string ExecuteCodeName = "execute_code";

    private static readonly JsonElement s_schema = JsonDocument.Parse(
        """
        {
          "type": "object",
          "properties": {
            "code": {
              "type": "string",
              "description": "Python code to execute locally in the agent environment."
            }
          },
          "required": ["code"]
        }
        """).RootElement;

    private readonly string _pythonExecutable;
    private readonly ProcessExecutionLimits _limits;
    private readonly Dictionary<string, string> _environment;
    private readonly List<AIFunction> _tools;
    private readonly string? _runnerScript;
    private readonly CodeValidator? _validator;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalExecuteCodeFunction"/> class.
    /// </summary>
    /// <param name="pythonExecutablePath">Path to the Python executable (required).</param>
    /// <param name="tools">Host tools available to generated code.</param>
    /// <param name="executionLimits">Resource limits for code execution.</param>
    /// <param name="environment">Environment variables to pass to subprocess.</param>
    /// <param name="runnerScript">Optional path to bundled Python runner script.</param>
    /// <param name="allowedImports">Custom allowed imports (replaces defaults).</param>
    /// <param name="blockedImports">Custom blocked imports (replaces defaults).</param>
    /// <param name="allowedBuiltins">Custom allowed builtins (replaces defaults).</param>
    /// <param name="blockedBuiltins">Custom blocked builtins (replaces defaults).</param>
    public LocalExecuteCodeFunction(
        string pythonExecutablePath,
        IEnumerable<AIFunction>? tools = null,
        ProcessExecutionLimits? executionLimits = null,
        IReadOnlyDictionary<string, string>? environment = null,
        string? runnerScript = null,
        string[]? allowedImports = null,
        string[]? blockedImports = null,
        string[]? allowedBuiltins = null,
        string[]? blockedBuiltins = null)
    {
        ArgumentNullException.ThrowIfNull(pythonExecutablePath);

        _pythonExecutable = pythonExecutablePath;
        _limits = executionLimits ?? new ProcessExecutionLimits();
        _environment = environment != null ? new Dictionary<string, string>(environment) : [];
        _tools = tools?.Where(t => t != null && t.Metadata.Name != ExecuteCodeName).ToList() ?? [];
        _runnerScript = runnerScript;

        // Create validator if validation lists are provided
        if (allowedImports != null || blockedImports != null || allowedBuiltins != null || blockedBuiltins != null)
        {
            _validator = new CodeValidator(
                _pythonExecutable,
                runnerScript,
                allowedImports,
                blockedImports,
                allowedBuiltins,
                blockedBuiltins);
        }

        Metadata = new AIFunctionMetadata(ExecuteCodeName)
        {
            Description = BuildDescription(),
            Parameters = [new AIFunctionParameterMetadata("code") { ParameterType = typeof(string), IsRequired = true, Schema = s_schema }],
        };
    }

    /// <inheritdoc/>
    public override AIFunctionMetadata Metadata { get; }

    /// <inheritdoc/>
    protected override async Task<object?> InvokeCoreAsync(
        IEnumerable<KeyValuePair<string, object?>> arguments,
        CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        var code = arguments.FirstOrDefault(a => a.Key == "code").Value as string
            ?? throw new ArgumentException("Missing required 'code' parameter.");

        // Validate code if validator is configured
        if (_validator != null)
        {
            await _validator.ValidateAsync(code, cancellationToken).ConfigureAwait(false);
        }

        // Execute code
        var bridge = new ProcessBridge(
            _tools,
            _limits,
            _environment,
            workingDirectory: null,
            _pythonExecutable,
            _runnerScript);

        var result = await bridge.RunAsync(code, cancellationToken).ConfigureAwait(false);

        // Convert result to content
        return BuildExecutionContents(result);
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        if (!_disposed)
        {
            _disposed = true;
        }
    }

    private string BuildDescription()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("Execute Python code locally in the agent environment.");

        if (_tools.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("Available host tools (call with `await tool_name(...)`):");
            foreach (var tool in _tools)
            {
                sb.AppendLine($"- {tool.Metadata.Name}: {tool.Metadata.Description ?? "No description"}");
            }
        }

        return sb.ToString();
    }

    private static List<ChatMessage> BuildExecutionContents(Dictionary<string, object?> result)
    {
        var stdout = result.TryGetValue("stdout", out var so) ? so?.ToString() ?? "" : "";
        var stderr = result.TryGetValue("stderr", out var se) ? se?.ToString() ?? "" : "";
        var outputPresent = result.TryGetValue("output_present", out var op) && Convert.ToBoolean(op);
        var output = result.TryGetValue("output", out var o) ? o : null;

        var messages = new List<ChatMessage>();

        if (!string.IsNullOrEmpty(stdout))
        {
            messages.Add(new ChatMessage(ChatRole.Tool, stdout));
        }

        if (!string.IsNullOrEmpty(stderr))
        {
            messages.Add(new ChatMessage(ChatRole.Tool, $"stderr: {stderr}"));
        }

        if (outputPresent && output != null)
        {
            var serialized = JsonSerializer.Serialize(output);
            messages.Add(new ChatMessage(ChatRole.Tool, serialized));
        }

        if (messages.Count == 0)
        {
            messages.Add(new ChatMessage(ChatRole.Tool, "Code executed successfully without output."));
        }

        return messages;
    }
}
