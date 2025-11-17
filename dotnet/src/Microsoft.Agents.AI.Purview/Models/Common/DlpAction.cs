// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Defines all the actions for DLP.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<DlpAction>))]
internal enum DlpAction
{
    /// <summary>
    /// The DLP action to notify user.
    /// </summary>
    NotifyUser,

    /// <summary>
    /// The DLP action is block.
    /// </summary>
    BlockAccess,

    /// <summary>
    /// The DLP action to apply restrictions on device.
    /// </summary>
    DeviceRestriction,

    /// <summary>
    /// The DLP action to apply restrictions on browsers.
    /// </summary>
    BrowserRestriction,

    /// <summary>
    /// The DLP action to generate an alert
    /// </summary>
    GenerateAlert,

    /// <summary>
    /// The DLP action to generate an incident report
    /// </summary>
    GenerateIncidentReportAction,

    /// <summary>
    /// The DLP action to block anonymous link access in SPO
    /// </summary>
    SPBlockAnonymousAccess,

    /// <summary>
    /// DLP Action to disallow guest access in SPO
    /// </summary>
    SPRuntimeAccessControl,

    /// <summary>
    /// DLP No Op action for NotifyUser. Used in Block Access V2 rule
    /// </summary>
    SPSharingNotifyUser,

    /// <summary>
    /// DLP No Op action for GIR. Used in Block Access V2 rule
    /// </summary>
    SPSharingGenerateIncidentReport,

    /// <summary>
    /// Restrict access action for data in motion scenarios.
    /// Advanced version of BlockAccess which can take both enforced restriction mode (Audit, Block, etc.)
    /// and action triggers (Print, SaveToLocal, etc.) as parameters.
    /// </summary>
    RestrictAccess,
}
