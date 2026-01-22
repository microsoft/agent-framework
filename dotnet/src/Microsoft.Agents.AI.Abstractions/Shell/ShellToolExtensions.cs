// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Extension methods for <see cref="ShellTool"/>.
/// </summary>
public static class ShellToolExtensions
{
    /// <summary>
    /// Converts a <see cref="ShellTool"/> to an <see cref="AIFunction"/> for use with agents.
    /// </summary>
    /// <param name="shellTool">The shell tool to convert.</param>
    /// <param name="timeoutInMilliseconds">Optional override for timeout in milliseconds. If null, uses <see cref="ShellToolOptions.TimeoutInMilliseconds"/>.</param>
    /// <param name="maxOutputLength">Optional override for max output length. If null, uses <see cref="ShellToolOptions.MaxOutputLength"/>.</param>
    /// <returns>An <see cref="AIFunction"/> that wraps the shell tool.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="shellTool"/> is null.</exception>
    /// <remarks>
    /// <para>
    /// The returned <see cref="AIFunction"/> accepts a <c>commands</c> parameter which is an array of
    /// shell commands to execute. The function returns a <see cref="ShellResultContent"/> containing
    /// the output for each command.
    /// </para>
    /// </remarks>
    public static AIFunction AsAIFunction(
        this ShellTool shellTool,
        int? timeoutInMilliseconds = null,
        int? maxOutputLength = null)
    {
        _ = Throw.IfNull(shellTool);

        return AIFunctionFactory.Create(
            async (
                [Description("List of shell commands to execute")]
                string[] commands,
                CancellationToken cancellationToken) =>
            {
                var callContent = new ShellCallContent(
                    Guid.NewGuid().ToString(),
                    commands)
                {
                    TimeoutInMilliseconds = timeoutInMilliseconds,
                    MaxOutputLength = maxOutputLength
                };

                return await shellTool.ExecuteAsync(callContent, cancellationToken).ConfigureAwait(false);
            },
            name: shellTool.Name,
            description: shellTool.Description);
    }
}
