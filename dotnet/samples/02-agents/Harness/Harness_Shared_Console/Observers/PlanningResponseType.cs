// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Specifies the type of planning response from the agent.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<PlanningResponseType>))]
public enum PlanningResponseType
{
    /// <summary>
    /// The agent needs clarification and presents options for the user to choose from.
    /// </summary>
    [Description("Use this type when you need clarification around the user request and you want to present the user with options to choose from.")]
    Clarification,

    /// <summary>
    /// The agent is seeking approval to proceed with execution.
    /// </summary>
    [Description("Use this type when you are ready to start execution, but need approval to start executing.")]
    Approval,
}
