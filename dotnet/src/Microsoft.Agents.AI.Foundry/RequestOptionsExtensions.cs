// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

internal static class RequestOptionsExtensions
{
    /// <summary>Gets the singleton <see cref="PipelinePolicy"/> that adds a MEAI user-agent header.</summary>
    internal static PipelinePolicy UserAgentPolicy => MeaiUserAgentPolicy.Instance;

    /// <summary>Creates a <see cref="RequestOptions"/> configured for use with Foundry Agents.</summary>
    public static RequestOptions ToRequestOptions(this CancellationToken cancellationToken, bool streaming)
    {
        RequestOptions requestOptions = new()
        {
            CancellationToken = cancellationToken,
            BufferResponse = !streaming
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
