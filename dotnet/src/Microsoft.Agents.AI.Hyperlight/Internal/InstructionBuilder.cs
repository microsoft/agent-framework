// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Builds the CodeAct guidance strings returned through
/// <see cref="AIContext.Instructions"/> and the <c>execute_code</c>
/// function description.
/// </summary>
internal static class InstructionBuilder
{
    /// <summary>
    /// Builds the short CodeAct guidance block that is merged into the
    /// agent's instructions for the current invocation.
    /// </summary>
    public static string BuildContextInstructions(bool toolsVisibleToModel)
    {
        if (toolsVisibleToModel)
        {
            return
                "You can execute code in a secure sandbox by calling the `execute_code` tool. "
                + "Use it for calculations, data analysis, and anything that benefits from running code. "
                + "State does not persist between calls; pass any required values in the code you execute.";
        }

        return
            "You can execute code in a secure sandbox by calling the `execute_code` tool. "
            + "Any tools listed in the tool's description are only accessible from within the sandbox "
            + "via `call_tool(\"<name>\", ...)` — they cannot be invoked directly. "
            + "State does not persist between calls; pass any required values in the code you execute.";
    }

    /// <summary>
    /// Builds the detailed description attached to the run-scoped
    /// <c>execute_code</c> <see cref="AIFunction"/>. This includes the
    /// available <c>call_tool</c> signatures and a capability summary.
    /// </summary>
    /// <remarks>
    /// Host-side filesystem paths are intentionally omitted from the
    /// description — only sandbox-visible mount paths are exposed to the
    /// model.
    /// </remarks>
    public static string BuildExecuteCodeDescription(
        IReadOnlyList<AIFunction> tools,
        IReadOnlyList<FileMount> fileMounts,
        IReadOnlyList<AllowedDomain> allowedDomains,
        bool hasHostInputDirectory)
    {
        var sb = new StringBuilder();
        sb.Append("Executes code in a secure Hyperlight sandbox. ");
        sb.Append("Pass the full source to execute via the `code` parameter. ");
        sb.Append("Returns a JSON string with `stdout`, `stderr`, `exit_code`, and `success` fields.");

        if (tools.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine();
            sb.AppendLine("The following host tools are available inside the sandbox via `call_tool(\"<name>\", **kwargs)`:");
            foreach (var tool in tools)
            {
                sb.Append("- `");
                sb.Append(tool.Name);
                sb.Append('`');
                if (!string.IsNullOrWhiteSpace(tool.Description))
                {
                    sb.Append(": ");
                    sb.Append(tool.Description);
                }

                sb.AppendLine();
            }
        }

        if (hasHostInputDirectory || fileMounts.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("Filesystem access:");
            if (hasHostInputDirectory)
            {
                sb.AppendLine("- Host input directory mounted read-only at `/input`.");
            }

            foreach (var mount in fileMounts)
            {
                sb.Append("- `");
                sb.Append(mount.MountPath);
                sb.AppendLine("`");
            }
        }

        if (allowedDomains.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("Outbound network access is restricted to the following targets:");
            foreach (var domain in allowedDomains)
            {
                sb.Append("- `");
                sb.Append(domain.Target);
                sb.Append('`');
                if (domain.Methods is { Count: > 0 })
                {
                    sb.Append(" [");
                    sb.Append(string.Join(", ", domain.Methods));
                    sb.Append(']');
                }

                sb.AppendLine();
            }
        }

        return sb.ToString().TrimEnd();
    }
}
