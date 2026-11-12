// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;

namespace Microsoft.Shared.Diagnostics;

/// <summary>Matches application-configured HTTP hosts and ports.</summary>
internal sealed class AllowedHttpHosts
{
    private readonly HashSet<string> _destinations = new(StringComparer.OrdinalIgnoreCase);

    public AllowedHttpHosts(IEnumerable<string> allowedHosts)
    {
        if (allowedHosts is null)
        {
            throw new ArgumentNullException(nameof(allowedHosts));
        }

        foreach (string host in allowedHosts)
        {
            string hostName = host;
            int port = 443;
            if (!string.IsNullOrWhiteSpace(host) && Uri.CheckHostName(host) == UriHostNameType.Unknown)
            {
                int separator = host.LastIndexOf(':');
                if (separator > 0 && (host.StartsWith("[", StringComparison.Ordinal) || host.IndexOf(':') == separator))
                {
                    hostName = host.Substring(0, separator);
                    if (!int.TryParse(host.Substring(separator + 1), NumberStyles.None, CultureInfo.InvariantCulture, out port))
                    {
                        port = -1;
                    }
                }
            }

            if (string.IsNullOrWhiteSpace(hostName) || Uri.CheckHostName(hostName) == UriHostNameType.Unknown ||
                port is < 1 or > 65535)
            {
                throw new ArgumentException("Allowed hosts must be DNS names or IP literals with an optional port from 1 to 65535, without schemes, paths, or wildcards. IPv6 literals with a port must be bracketed.", nameof(allowedHosts));
            }

            this._destinations.Add(NormalizeDestination(new UriBuilder(Uri.UriSchemeHttps, hostName, port).Uri));
        }
    }

    public bool Contains(Uri uri) => this._destinations.Contains(NormalizeDestination(uri));

    private static string NormalizeDestination(Uri uri) =>
        $"{uri.IdnHost.TrimEnd('.')}:{uri.Port.ToString(CultureInfo.InvariantCulture)}";
}
