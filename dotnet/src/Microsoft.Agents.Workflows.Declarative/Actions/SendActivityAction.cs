// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Handlers;

internal sealed class SendActivityAction : ProcessAction<SendActivity>
{
    private readonly TextWriter _activityWriter;

    public SendActivityAction(SendActivity source, TextWriter activityWriter)
        : base(source)
    {
        this._activityWriter = activityWriter;
    }

    protected override Task HandleAsync(ProcessActionContext context, CancellationToken cancellationToken)
    {
        Console.WriteLine($"\nACTIVITY: {this.Model.Activity?.GetType().Name ?? "Unknown"}"); // %%% LOGGER

        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            try
            {
                if (!string.IsNullOrEmpty(messageActivity.Summary))
                {
                    this._activityWriter.WriteLine($"\t{messageActivity.Summary}");
                }

                string? activityText = context.Engine.Format(messageActivity.Text);
                this._activityWriter.WriteLine(activityText + Environment.NewLine);
            }
            finally
            {
                Console.ResetColor();
            }
        }

        return Task.CompletedTask;
    }
}
