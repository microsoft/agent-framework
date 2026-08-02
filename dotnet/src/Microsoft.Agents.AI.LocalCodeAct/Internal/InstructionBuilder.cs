// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

internal static class InstructionBuilder
{
    public static string BuildContextInstructions() =>
        "You can execute Python code locally by calling the `execute_code` tool. "
        + "Any tools listed in the tool's description are only accessible from within the executed "
        + "code via `await call_tool(\"<name>\", **kwargs)` — they cannot be invoked directly. "
        + "State does not persist between calls; pass any required values in the code you execute.";

    public static string BuildExecuteCodeDescription(
        IReadOnlyList<AIFunction> tools,
        IReadOnlyList<FileMount> fileMounts)
    {
        var sb = new StringBuilder();
        sb.Append("Executes Python code locally in the agent environment. ");
        sb.Append("Pass the full source to execute via the `code` parameter. ");
        sb.Append("Returns the captured stdout/stderr and the value of a top-level `result` variable when set.");

        if (tools.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine();
            sb.AppendLine("The following host tools are available inside the executed code via `await call_tool(\"<name>\", **kwargs)`:");
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

        if (fileMounts.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("Filesystem access (host paths are exposed directly; mount paths shown are for description):");
            foreach (var mount in fileMounts)
            {
                sb.Append("- `");
                sb.Append(mount.MountPath);
                sb.Append("` -> `");
                sb.Append(mount.HostPath);
                sb.Append("` (");
                sb.Append(mount.Mode);
                sb.AppendLine(")");
            }
        }

        return sb.ToString().TrimEnd();
    }
}
