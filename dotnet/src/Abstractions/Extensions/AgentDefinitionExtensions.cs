// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;

namespace Microsoft.Agents;

/// <summary>
/// Provides extension methods for <see cref="AgentDefinition"/>.
/// </summary>

public static class AgentDefinitionExtensions
{
    /// <summary>
    /// Get the first tool definition of the specified type.
    /// </summary>
    /// <param name="agentDefinition">Agent definition to retrieve the first tool from.</param>
    /// <param name="toolType">Tool type</param>
    public static AgentToolDefinition? GetFirstToolDefinition(this AgentDefinition agentDefinition, string toolType)
    {
        Verify.NotNull(agentDefinition);
        Verify.NotNull(toolType);
        return agentDefinition.Tools?.FirstOrDefault(tool => tool.Type == toolType);
    }

    /// <summary>
    /// Get all of the tool definitions of the specified type.
    /// </summary>
    /// <param name="agentDefinition">Agent definition to retrieve the tools from.</param>
    /// <param name="toolType">Tool type</param>
    public static IEnumerable<AgentToolDefinition>? GetToolDefinitions(this AgentDefinition agentDefinition, string toolType)
    {
        Verify.NotNull(agentDefinition);
        Verify.NotNull(toolType);
        return agentDefinition.Tools?.Where(tool => tool.Type == toolType);
    }

    /// <summary>
    /// Determines if the agent definition has a tool of the specified type.
    /// </summary>
    /// <param name="agentDefinition">Agent definition</param>
    /// <param name="toolType">Tool type</param>
    public static bool HasToolType(this AgentDefinition agentDefinition, string toolType)
    {
        Verify.NotNull(agentDefinition);

        return agentDefinition.Tools?.Any(tool => tool?.Type?.Equals(toolType, System.StringComparison.Ordinal) ?? false) ?? false;
    }
}
