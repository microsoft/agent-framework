// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Represents the configuration settings for a Purview application, including tenant information, application name, and
/// optional default user settings.
/// </summary>
/// <remarks>This class is used to encapsulate the necessary configuration details for interacting with Purview
/// services. It includes the tenant ID and application name, which are required, and an optional default user ID that
/// can be used for requests where a specific user ID is not provided.</remarks>
public class PurviewSettings
{
    /// <summary>
    /// Initializes a new instance of the <see cref="PurviewSettings"/> class.
    /// </summary>
    /// <param name="appName">The publicly visible name of the application.</param>
    public PurviewSettings(string appName)
    {
        this.AppName = appName;
    }

    /// <summary>
    /// The publicly visible app name of the application.
    /// </summary>
    public string AppName { get; set; }

    /// <summary>
    /// The version string of the application.
    /// </summary>
    public string? AppVersion { get; set; }

    /// <summary>
    /// The tenant id of the user making the request.
    /// If this is not provided, the tenant id will be inferred from the token.
    /// </summary>
    public string? TenantId { get; set; }

    /// <summary>
    /// Gets or sets the location of the Purview resource.
    /// If this is not provided, a location containing the client id will be used instead.
    /// </summary>
    public PurviewAppLocation? PurviewAppLocation { get; set; }

    /// <summary>
    /// Gets or sets a flag indicating whether to ignore exceptions when processing Purview requests. False by default.
    /// If set to true, exceptions calling Purview will be logged but not thrown.
    /// </summary>
    public bool IgnoreExceptions { get; set; }

    /// <summary>
    /// Gets or sets the base URI for the Microsoft Graph API.
    /// Set to graph v1.0 by default.
    /// </summary>
    public Uri GraphBaseUri { get; set; } = new Uri("https://graph.microsoft.com/v1.0/");

    /// <summary>
    /// Gets or sets the message to display when a prompt is blocked by Purview policies.
    /// </summary>
    public string BlockedPromptMessage { get; set; } = "Prompt blocked by policies";

    /// <summary>
    /// Gets or sets the message to display when a response is blocked by Purview policies.
    /// </summary>
    public string BlockedResponseMessage { get; set; } = "Response blocked by policies";

    /// <summary>
    /// The size limit of the default in memory cache in bytes. This only applies if no cache is provided when creating Purview resources.
    /// </summary>
    public long? InMemoryCacheSizeLimit { get; set; } = 100_000_000;

    /// <summary>
    /// The TTL of each cache entry.
    /// </summary>
    public TimeSpan CacheTTL { get; set; } = TimeSpan.FromMinutes(30);

    /// <summary>
    /// The maximum number of background jobs that can be queued up.
    /// </summary>
    public int PendingBackgroundJobLimit { get; set; } = 100;

    /// <summary>
    /// The maximum number of concurrent job consumers.
    /// </summary>
    public int MaxConcurrentJobConsumers { get; set; } = 10;
}
