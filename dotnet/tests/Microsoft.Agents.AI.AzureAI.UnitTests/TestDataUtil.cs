// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.IO;
using Azure.AI.Projects.OpenAI;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

/// <summary>
/// Utility class for loading and processing test data files.
/// </summary>
internal static class TestDataUtil
{
    private static readonly string s_agentResponseJson = File.ReadAllText("TestData/AgentResponse.json");
    private static readonly string s_agentVersionResponseJson = File.ReadAllText("TestData/AgentVersionResponse.json");
    private static readonly string s_openAIDefaultResponseJson = File.ReadAllText("TestData/OpenAIDefaultResponse.json");

    private const string AgentDefinitionPlaceholder = "\"agent-definition-placeholder\"";

    private const string DefaultAgentDefinition = """
            {
              "kind": "prompt",
              "model": "gpt-5-mini",
              "instructions": "You are a storytelling agent. You craft engaging one-line stories based on user prompts and context.",
              "tools": []
            }
        """;

    /// <summary>
    /// Gets the agent response JSON with optional placeholder replacements applied.
    /// </summary>
    public static string GetAgentResponseJson(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        return json;
    }

    /// <summary>
    /// Gets the agent version response JSON with optional placeholder replacements applied.
    /// </summary>
    public static string GetAgentVersionResponseJson(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentVersionResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        return json;
    }

    /// <summary>
    /// Gets the agent version response JSON with empty version and ID fields for testing hosted agents like MCP agents.
    /// </summary>
    public static string GetAgentVersionResponseJsonWithEmptyVersion(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentVersionResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        // Remove the version and id fields to simulate hosted agents without version
        json = json.Replace("\"version\": \"1\",", "\"version\": \"\",");
        json = json.Replace("\"id\": \"agent_abc123:1\",", "\"id\": \"\",");
        return json;
    }

    /// <summary>
    /// Gets the agent response JSON with empty version and ID fields in the latest version for testing hosted agents like MCP agents.
    /// </summary>
    public static string GetAgentResponseJsonWithEmptyVersion(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        // Remove the version and id fields to simulate hosted agents without version
        json = json.Replace("\"version\": \"1\",", "\"version\": \"\",");
        json = json.Replace("\"id\": \"agent_abc123:1\",", "\"id\": \"\",");
        return json;
    }

    /// <summary>
    /// Gets the agent version response JSON with whitespace-only version and ID fields for testing hosted agents like MCP agents.
    /// </summary>
    public static string GetAgentVersionResponseJsonWithWhitespaceVersion(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentVersionResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        // Use whitespace-only version and id fields to simulate hosted agents without version
        return json
            .Replace("\"version\": \"1\",", "\"version\": \"   \",")
            .Replace("\"id\": \"agent_abc123:1\",", "\"id\": \"   \",");
    }

    /// <summary>
    /// Gets the agent response JSON with whitespace-only version and ID fields in the latest version for testing hosted agents like MCP agents.
    /// </summary>
    public static string GetAgentResponseJsonWithWhitespaceVersion(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_agentResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        // Use whitespace-only version and id fields to simulate hosted agents without version
        return json
            .Replace("\"version\": \"1\",", "\"version\": \"   \",")
            .Replace("\"id\": \"agent_abc123:1\",", "\"id\": \"   \",");
    }

    /// <summary>
    /// Gets the OpenAI default response JSON with optional placeholder replacements applied.
    /// </summary>
    public static string GetOpenAIDefaultResponseJson(string? agentName = null, AgentDefinition? agentDefinition = null, string? instructions = null, string? description = null)
    {
        var json = s_openAIDefaultResponseJson;
        json = ApplyAgentName(json, agentName);
        json = ApplyAgentDefinition(json, agentDefinition);
        json = ApplyInstructions(json, instructions);
        json = ApplyDescription(json, description);
        return json;
    }

    private static string ApplyAgentName(string json, string? agentName)
    {
        if (!string.IsNullOrEmpty(agentName))
        {
            return json.Replace("\"agent_abc123\"", $"\"{agentName}\"");
        }
        return json;
    }

    private static string ApplyAgentDefinition(string json, AgentDefinition? definition)
    {
        return (definition is not null)
            ? json.Replace(AgentDefinitionPlaceholder, ModelReaderWriter.Write(definition).ToString())
            : json.Replace(AgentDefinitionPlaceholder, DefaultAgentDefinition);
    }

    private static string ApplyInstructions(string json, string? instructions)
    {
        if (!string.IsNullOrEmpty(instructions))
        {
            return json.Replace("You are a storytelling agent. You craft engaging one-line stories based on user prompts and context.", instructions);
        }
        return json;
    }

    private static string ApplyDescription(string json, string? description)
    {
        if (!string.IsNullOrEmpty(description))
        {
            return json.Replace("\"description\": \"\"", $"\"description\": \"{description}\"");
        }
        return json;
    }
}
