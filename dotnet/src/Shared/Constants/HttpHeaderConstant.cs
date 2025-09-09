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
        /// <summary>User agent string to use for all HTTP requests issued by Semantic Kernel.</summary>
        public static string UserAgent => "agent-framework-dotnet";

        /// <summary>
        /// Gets the version of the <see cref="System.Reflection.Assembly"/> in which the specific type is declared.
        /// </summary>
        /// <param name="type">Type for which the assembly version is returned.</param>
        public static string GetAssemblyVersion(Type type)
        {
            return $"dotnet/{type.Assembly.GetName().Version!}";
        }
    }
}
