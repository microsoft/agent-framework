// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005 // Using directive is unnecessary.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Shared.Constants;

/// <summary>Provides HTTP header names and values for common purposes.</summary>
[ExcludeFromCodeCoverage]
internal static class HttpHeaderConstant
{
    public static class Names
    {
        /// <summary>HTTP header name to use to include the Semantic Kernel package version in all HTTP requests issued by Semantic Kernel.</summary>
        public static string AgentFrameworkVersion => "agent-framework-version";

        /// <summary>HTTP User-Agent header name.</summary>
        public static string UserAgent => "User-Agent";
    }

    public static class Values
    {
        // Cache the versions for the types we query to avoid repeated reflection calls for each request.
        private static readonly Dictionary<Type, string> s_versionCache = [];

        /// <summary>User agent string to use for all HTTP requests issued by Semantic Kernel.</summary>
        public static string GetUserAgent(Type type) => $"agent-framework-dotnet/{GetAssemblyVersion(type)}";

        public static string GetAgentFrameworkVersion(Type type) => $"dotnet/{GetAssemblyVersion(type)}";

        /// <summary>
        /// Gets the version of the <see cref="System.Reflection.Assembly"/> in which the specific type is declared.
        /// </summary>
        /// <param name="type">Type for which the assembly version is returned.</param>
        private static string GetAssemblyVersion(Type type)
        {
            if (!s_versionCache.TryGetValue(type, out var foundVersion))
            {
                foundVersion = type.Assembly.GetName().Version!.ToString();
                s_versionCache[type] = foundVersion;
            }

            return foundVersion;
        }
    }
}
