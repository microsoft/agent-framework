// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Pipeline policy that captures the <c>x-ms-served-model</c> response header from Azure OpenAI
/// and stores it in <see cref="ServedModelScope"/> for consumption by <see cref="FoundryChatClient"/>.
/// </summary>
/// <remarks>
/// <para>
/// Azure OpenAI Responses API returns the deployment alias in <c>response.model</c> but the actual
/// model snapshot (e.g. <c>gpt-5-nano-2025-08-07</c>) in the <c>x-ms-served-model</c> response header.
/// This policy extracts the header after the HTTP roundtrip so the <see cref="FoundryChatClient"/>
/// can overwrite <c>ChatResponse.ModelId</c> with the true model name.
/// </para>
/// <para>
/// Registered once per <c>OpenAIRequestPolicies</c> instance via the MEAI 10.5.1 extension hook.
/// When the header is absent (non-Azure endpoints), the scope is not set and the
/// <see cref="FoundryChatClient"/> preserves the original model name.
/// </para>
/// </remarks>
internal sealed class ServedModelPolicy : PipelinePolicy
{
    /// <summary>The Azure OpenAI response header that carries the actual served model name.</summary>
    internal const string ServedModelHeader = "x-ms-served-model";

    public static ServedModelPolicy Instance { get; } = new ServedModelPolicy();

    private ServedModelPolicy()
    {
    }

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        ProcessNext(message, pipeline, currentIndex);
        CaptureServedModel(message);
    }

    public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
        CaptureServedModel(message);
    }

    private static void CaptureServedModel(PipelineMessage message)
    {
        if (message.Response is null)
        {
            return;
        }

        if (message.Response.Headers.TryGetValue(ServedModelHeader, out string? servedModel)
            && !string.IsNullOrWhiteSpace(servedModel))
        {
            // Write into the box (reference-type mutation) so the value is visible to the
            // FoundryChatClient that pushed the box before calling the inner client.
            if (ServedModelScope.Current is { } box)
            {
                box.Value = servedModel.Trim();
            }
        }
    }
}
