// Copyright (c) Microsoft. All rights reserved.

using System.IO;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Utility class for loading toolbox-related test data files.
/// </summary>
internal static class TestDataUtil
{
    private static readonly string s_toolboxRecordResponseJson = File.ReadAllText("TestData/ToolboxRecordResponse.json");
    private static readonly string s_toolboxVersionResponseJson = File.ReadAllText("TestData/ToolboxVersionResponse.json");
    private static readonly string s_toolboxVersionWithDecorationFieldsJson = File.ReadAllText("TestData/ToolboxVersionWithDecorationFields.json");

    /// <summary>
    /// Gets the toolbox record response JSON.
    /// </summary>
    public static string GetToolboxRecordResponseJson() => s_toolboxRecordResponseJson;

    /// <summary>
    /// Gets the toolbox version response JSON.
    /// </summary>
    public static string GetToolboxVersionResponseJson() => s_toolboxVersionResponseJson;

    /// <summary>
    /// Gets the toolbox version response JSON with decoration fields on tools.
    /// </summary>
    public static string GetToolboxVersionWithDecorationFieldsJson() => s_toolboxVersionWithDecorationFieldsJson;
}
