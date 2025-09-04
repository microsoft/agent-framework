// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

/// <summary>
/// %%% COMMENT
/// </summary>
public static class IWorkflowContextExtensions
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="context"></param>
    /// <param name="lines"></param>
    /// <returns></returns>
    public static async ValueTask<string> FormatAsync(this IWorkflowContext context, params string[] lines)
    {
        DeclarativeWorkflowState state = new(RecalcEngineFactory.Create());
        await state.RestoreAsync(context, cancellationToken: default).ConfigureAwait(false);

        StringBuilder builder = new();
        foreach (string line in lines)
        {
            builder.AppendLine(state.Format(TemplateLine.Parse(line)));
        }

        return builder.ToString();
    }
}
