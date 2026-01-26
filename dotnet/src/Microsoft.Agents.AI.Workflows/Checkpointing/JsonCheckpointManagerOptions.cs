// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Options for configuring JSON serialization behavior in the checkpoint manager.
/// </summary>
public sealed class JsonCheckpointManagerOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether JSON deserialization should allow
    /// metadata properties (such as $type) to appear in any position within a JSON object.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set to <see langword="true"/>, the JSON deserializer will accept metadata properties
    /// regardless of their position in the JSON object. This is useful when working with databases
    /// like PostgreSQL that use <c>jsonb</c> columns, which do not preserve property order.
    /// </para>
    /// <para>
    /// The default value is <see langword="false"/>, which requires metadata properties to appear
    /// first in the JSON object as per the System.Text.Json default behavior.
    /// </para>
    /// </remarks>
    /// <seealso href="https://github.com/microsoft/agent-framework/issues/2962"/>
    public bool AllowOutOfOrderMetadataProperties { get; set; }
}
