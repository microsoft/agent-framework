// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ClientModel.Primitives;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.FoundryMemory;

internal static class RequestOptionsExtensions
{
    /// <summary>Creates a <see cref="RequestOptions"/> configured with MEAI user-agent tracking for Foundry Memory operations.</summary>
    public static RequestOptions ToRequestOptions(this CancellationToken cancellationToken)
    {
        RequestOptions requestOptions = new()
        {
            CancellationToken = cancellationToken,
            BufferResponse = true
        };

        requestOptions.AddPolicy(MeaiUserAgentPolicy.Instance, PipelinePosition.PerCall);

        return requestOptions;
    }

    /// <summary>Provides a pipeline policy that adds a "MEAI/x.y.z" user-agent header.</summary>
    private sealed class MeaiUserAgentPolicy : PipelinePolicy
    {
        public static MeaiUserAgentPolicy Instance { get; } = new MeaiUserAgentPolicy();

        private static readonly string s_userAgentValue = CreateUserAgentValue();

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            AddUserAgentHeader(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            AddUserAgentHeader(message);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }

        private static void AddUserAgentHeader(PipelineMessage message) =>
            message.Request.Headers.Add("User-Agent", s_userAgentValue);

        private static string CreateUserAgentValue()
        {
            const string Name = "MEAI";

            if (typeof(MeaiUserAgentPolicy).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
            {
                int pos = version.IndexOf('+');
                if (pos >= 0)
                {
                    version = version.Substring(0, pos);
                }

                if (version.Length > 0)
                {
                    return $"{Name}/{version}";
                }
            }

            return Name;
        }
    }
}
