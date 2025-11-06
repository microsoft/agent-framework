// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Represents configuration options for the HTTP trigger for an agent.
/// </summary>
/// <remarks>
/// Initializes a new instance of the <see cref="HttpTriggerOptions"/> class.
/// </remarks>
/// <param name="isEnabled">Indicates whether the HTTP trigger is enabled for the agent.</param>
public sealed class HttpTriggerOptions(bool isEnabled)
{
    /// <summary>
    /// Gets or sets a value indicating whether the HTTP trigger is enabled for the agent.
    /// </summary>
    public bool IsEnabled { get; set; } = isEnabled;
}
