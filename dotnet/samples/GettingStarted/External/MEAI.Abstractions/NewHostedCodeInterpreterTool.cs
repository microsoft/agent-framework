// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace OpenAI.Assistants;

/// <summary>
/// Proposal for abstraction updates based on the common code interpreter tool properties.
/// Based on the decision, the <see cref="HostedCodeInterpreterTool"/> abstraction can be updated in M.E.AI directly.
/// </summary>
public class NewHostedCodeInterpreterTool : HostedCodeInterpreterTool
{
    // Usage of an internal dictionary is temporary and only used here because the MEAI.Abstractions does not have this specialization yet and the
    // ChatClients must rely on the AdditionalProperties to check and set correctly the Code Interpreter Resource avoiding a customized RawRepresentationFactory implementation.
    private readonly Dictionary<string, object?> _additionalProperties = [];

    /// <summary>Gets or sets the list of file IDs that the code interpreter tool can access.</summary>
    public IList<string> FileIds
    {
        get
        {
            // Only create the property in the dictionary when it is actually used
            if (!this._additionalProperties.TryGetValue("fileIds", out var value) || value is null)
            {
                value = new List<string>();
                this._additionalProperties["fileIds"] = value;
            }

            return (IList<string>)value;
        }
    }

    /// <inheritdoc/>
    public override IReadOnlyDictionary<string, object?> AdditionalProperties => this._additionalProperties;
}
