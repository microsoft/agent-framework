// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace OpenAI.Assistants;

/// <summary>
/// Proposal for abstraction updates based on the common file search tool properties.
/// This provides a standardized interface for file search functionality across providers.
/// </summary>
public class NewHostedFileSearchTool : AITool
{
    // Usage of an internal dictionary is temporary and only used here because the MEAI.Abstractions does not have this specialization yet and the
    // ChatClients must rely on the AdditionalProperties to check and set correctly the File Search Resource avoiding a customized RawRepresentationFactory implementation.
    private readonly Dictionary<string, object?> _additionalProperties = [];

    /// <summary>Gets or sets the list of vector store IDs that the file search tool can access.</summary>
    public IList<string> VectorStoreIds
    {
        get
        {
            // Only create the property in the dictionary when it is actually used
            if (!this._additionalProperties.TryGetValue("vectorStoreIds", out var value) || value is null)
            {
                value = new List<string>();
                this._additionalProperties["vectorStoreIds"] = value;
            }

            return (IList<string>)value;
        }
    }

    /// <inheritdoc/>
    public override IReadOnlyDictionary<string, object?> AdditionalProperties => this._additionalProperties;
}
