// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="AgentTaskStatus"/> class.
/// </summary>
internal static class A2AAgentTaskStatusExtensions
{
    internal static IList<AIContent> GetUserInputRequests(this AgentTaskStatus status)
    {
        List<AIContent> contents = [];

        if (status.Message is null)
        {
            return contents;
        }

        foreach (var part in status.Message.Parts)
        {
            if (status.State == TaskState.InputRequired && part is TextPart textPart)
            {
                var content = new TextInputRequestContent(Guid.NewGuid().ToString())
                {
                    Text = textPart.Text,
                    RawRepresentation = part,
                    AdditionalProperties = part.Metadata.ToAdditionalProperties(),
                };

                contents.Add(content);
            }
        }

        return contents;
    }
}
