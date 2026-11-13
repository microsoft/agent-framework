// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;

namespace Microsoft.Shared.Diagnostics;

/// <summary>Matches application-configured HTTP hosts and ports.</summary>
internal sealed class AllowedHttpHosts
{
    private readonly HashSet<string> _destinations = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _anyPortHosts = new(StringComparer.OrdinalIgnoreCase);

    public AllowedHttpHosts(IEnumerable<string> allowedHosts)
        : this(allowedHosts, allowAnyPortWhenUnspecified: false)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="AllowedHttpHosts"/> class.</summary>
    /// <param name="allowedHosts">DNS names or IP literals, each with an optional port.</param>
    /// <param name="allowAnyPortWhenUnspecified">
    /// When <see langword="true"/>, an entry without a port allows any port on that host.
    /// When <see langword="false"/>, an entry without a port allows only port 443.
    /// </param>
    public AllowedHttpHosts(IEnumerable<string> allowedHosts, bool allowAnyPortWhenUnspecified)
    {
        if (allowedHosts is null)
        {
            throw new ArgumentNullException(nameof(allowedHosts));
        }

        foreach (string host in allowedHosts)
        {
            string hostName = host;
            int port = 443;
            bool hasPort = false;
            if (!string.IsNullOrWhiteSpace(host) && Uri.CheckHostName(host) == UriHostNameType.Unknown)
            {
                int separator = host.LastIndexOf(':');
                if (separator > 0 && (host.StartsWith("[", StringComparison.Ordinal) || host.IndexOf(':') == separator))
                {
                    hostName = host.Substring(0, separator);
                    hasPort = true;
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

            Uri destination = new UriBuilder(Uri.UriSchemeHttps, hostName, port).Uri;
            if (allowAnyPortWhenUnspecified && !hasPort)
            {
                this._anyPortHosts.Add(NormalizeHost(destination));
            }
            else
            {
                this._destinations.Add(NormalizeDestination(destination));
            }
        }
    }

    public bool Contains(Uri uri) =>
        this._destinations.Contains(NormalizeDestination(uri)) || this._anyPortHosts.Contains(NormalizeHost(uri));

    private static string NormalizeHost(Uri uri) => uri.IdnHost.TrimEnd('.');

    private static string NormalizeDestination(Uri uri) =>
        $"{NormalizeHost(uri)}:{uri.Port.ToString(CultureInfo.InvariantCulture)}";
}
