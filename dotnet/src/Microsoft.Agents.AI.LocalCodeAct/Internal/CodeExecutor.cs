// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Coordinates a single execution: optional validation, snapshot of writable mounts,
/// running the subprocess, capturing written files, and assembling the final content list.
/// </summary>
internal sealed class CodeExecutor
{
    private readonly string _pythonExecutable;
    private readonly string _runnerScript;
    private readonly CodeValidator? _validator;
    private readonly ProcessExecutionLimits _limits;
    private readonly IReadOnlyDictionary<string, string>? _environment;
    private readonly string? _workingDirectory;

    public CodeExecutor(
        string pythonExecutable,
        string runnerScript,
        CodeValidator? validator,
        ProcessExecutionLimits limits,
        IReadOnlyDictionary<string, string>? environment,
        string? workingDirectory)
    {
        this._pythonExecutable = pythonExecutable;
        this._runnerScript = runnerScript;
        this._validator = validator;
        this._limits = limits;
        this._environment = environment;
        this._workingDirectory = workingDirectory;
    }

    /// <summary>Immutable snapshot of provider state captured at the start of an invocation.</summary>
    public sealed class RunSnapshot
    {
        public RunSnapshot(IReadOnlyList<AIFunction> tools, IReadOnlyList<FileMount> fileMounts)
        {
            this.Tools = tools;
            this.FileMounts = fileMounts;
        }

        public IReadOnlyList<AIFunction> Tools { get; }

        public IReadOnlyList<FileMount> FileMounts { get; }
    }

    public async Task<List<AIContent>> ExecuteAsync(RunSnapshot snapshot, string code, CancellationToken cancellationToken)
    {
        if (this._validator is not null)
        {
            await this._validator.ValidateAsync(code, cancellationToken).ConfigureAwait(false);
        }

        var preState = FileMountHelper.SnapshotWritableMounts(snapshot.FileMounts);

        var bridge = new ProcessBridge(
            this._pythonExecutable,
            this._runnerScript,
            snapshot.Tools,
            this._limits,
            this._environment,
            this._workingDirectory);

        var result = await bridge.RunAsync(code, cancellationToken).ConfigureAwait(false);

        var captured = FileMountHelper.CaptureWrittenFiles(snapshot.FileMounts, preState, this._limits);

        return BuildContents(result, captured);
    }

    private static List<AIContent> BuildContents(ProcessBridge.ExecutionResult result, List<AIContent> capturedFiles)
    {
        var contents = new List<AIContent>();

        if (!string.IsNullOrEmpty(result.Stdout))
        {
            var stdoutText = result.StdoutTruncated ? result.Stdout + "\n[stdout truncated]" : result.Stdout;
            contents.Add(new TextContent(stdoutText));
        }

        if (!string.IsNullOrEmpty(result.Stderr))
        {
            var stderrText = result.StderrTruncated ? result.Stderr + "\n[stderr truncated]" : result.Stderr;
            contents.Add(new TextContent("stderr:\n" + stderrText));
        }

        if (result.OutputPresent && result.Output.HasValue)
        {
            contents.Add(new TextContent("result:\n" + result.Output.Value.GetRawText()));
        }

        contents.AddRange(capturedFiles);

        if (contents.Count == 0)
        {
            contents.Add(new TextContent("Code executed successfully without output."));
        }

        return contents;
    }
}
