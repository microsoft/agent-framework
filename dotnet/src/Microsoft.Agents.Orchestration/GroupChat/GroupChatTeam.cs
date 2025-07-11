// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Describes a team of agents participating in a group chat.
/// </summary>
public sealed class GroupChatTeam : Dictionary<string, (string Type, string Description)>
{
    /// <summary>
    /// Format the names of the agents in the team as a comma delimimted list.
    /// </summary>
    /// <returns>A comma delimimted list of agent name.</returns>
    public string FormatNames() => string.Join(",", this.Select(t => t.Key));

    /// <summary>
    /// Format the names and descriptions of the agents in the team as a markdown list.
    /// </summary>
    /// <returns>A markdown list of agent names and descriptions.</returns>
    public string FormatList() => string.Join(Environment.NewLine, this.Select(t => $"- {t.Key}: {t.Value.Description}"));
}
