// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Configures a <see cref="JevDecisionClient"/> and the client pipeline that sends its requests to the TypeSafe System
/// One API.
/// </summary>
/// <remarks>
/// <para>
/// This type follows the <see cref="ClientPipelineOptions"/> pattern of the OpenAI and Azure AI client libraries:
/// <see cref="ClientPipelineOptions.Transport"/> selects the HTTP stack, <see cref="ClientPipelineOptions.RetryPolicy"/>
/// controls retries, and <see cref="ClientPipelineOptions.AddPolicy(PipelinePolicy, PipelinePosition)"/> adds custom
/// policies. Unset pipeline settings get the defaults of the official TypeSafe SDK, as described for
/// <see cref="JevAIToolOptions"/>.
/// </para>
/// <para>
/// Like other client options, an instance becomes read-only once a client has been created with it.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class JevDecisionClientOptions : ClientPipelineOptions
{
    /// <inheritdoc />
    public override void Freeze()
    {
        JevPipelineDefaults.Apply(this);
        base.Freeze();
    }

    /// <summary>
    /// Gets or sets the System One endpoint. When <see langword="null"/>, <c>https://api.typesafe.ai/v1/systemone</c> is used.
    /// </summary>
    public Uri? Endpoint
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    }

    /// <summary>
    /// Gets or sets the Jev model that answers the questions, unless
    /// <see cref="Extensions.AI.DecisionOptions.ModelId"/> selects another for a request. Defaults to <c>jev-latest</c>.
    /// </summary>
    public string ModelId
    {
        get;
        set
        {
            this.AssertNotFrozen();
            field = value;
        }
    } = JevPipelineDefaults.DefaultModelId;
}
