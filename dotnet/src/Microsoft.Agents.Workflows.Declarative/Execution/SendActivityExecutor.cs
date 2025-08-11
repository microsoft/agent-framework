// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class SendActivityExecutor(SendActivity model, TextWriter activityWriter) :
    WorkflowActionExecutor<SendActivity>(model)
{
    protected override ValueTask ExecuteAsync(CancellationToken cancellationToken)
    {
        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            try
            {
                if (!string.IsNullOrEmpty(messageActivity.Summary))
                {
                    activityWriter.WriteLine($"\t{messageActivity.Summary}");
                }

                string? activityText = this.Context.Engine.Format(messageActivity.Text)?.Trim();
                activityWriter.WriteLine(activityText + Environment.NewLine);
            }
            finally
            {
                Console.ResetColor();
            }
        }

        return new ValueTask();
    }
}
