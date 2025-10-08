// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="Connection"/>.
/// </summary>
public static class ConnectionExtensions
{
    /// <summary>
    /// Retrieves the 'endpoint' property from a <see cref="Connection"/>.
    /// </summary>
    /// <param name="connection">Instance of <see cref="Connection"/></param>
    public static string? GetEndpoint(this Connection connection)
    {
        Throw.IfNull(connection);

        return connection.ExtensionData?.GetString("endpoint");
    }

    /// <summary>
    /// Retrieves the 'deployment_name' property from a <see cref="Connection"/>.
    /// </summary>
    /// <param name="connection">Instance of <see cref="Connection"/></param>
    public static string? GetDeploymentName(this Connection connection)
    {
        Throw.IfNull(connection);

        return connection.ExtensionData?.GetString("deployment_name");
    }
}
