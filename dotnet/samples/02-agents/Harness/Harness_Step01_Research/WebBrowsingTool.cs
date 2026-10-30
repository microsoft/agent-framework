// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// An AI function that downloads HTML pages and converts them to markdown.
/// Access is controlled by <see cref="WebBrowsingToolOptions"/> — by default, no hosts are accessible.
/// </summary>
internal sealed partial class WebBrowsingTool : AIFunction
{
    private const int MaxRedirects = 10;
    private readonly AIFunction _inner;
    private readonly WebBrowsingToolOptions _options;
    private readonly Func<string, CancellationToken, Task<IPAddress[]>> _resolveHostAddressesAsync;

    /// <summary>
    /// Initializes a new instance of the <see cref="WebBrowsingTool"/> class.
    /// </summary>
    /// <param name="options">Options controlling which URLs are permitted. By default, no hosts are accessible.</param>
    public WebBrowsingTool(WebBrowsingToolOptions options)
        : this(options, Dns.GetHostAddressesAsync)
    {
    }

    internal WebBrowsingTool(
        WebBrowsingToolOptions options,
        Func<string, CancellationToken, Task<IPAddress[]>> resolveHostAddressesAsync)
    {
        this._options = options ?? throw new ArgumentNullException(nameof(options));
        this._resolveHostAddressesAsync = resolveHostAddressesAsync ??
            throw new ArgumentNullException(nameof(resolveHostAddressesAsync));
        this._inner = AIFunctionFactory.Create(this.DownloadUriAsync);
    }

    /// <inheritdoc/>
    public override string Name => this._inner.Name;

    /// <inheritdoc/>
    public override string Description => this._inner.Description;

    /// <inheritdoc/>
    public override JsonElement JsonSchema => this._inner.JsonSchema;

    /// <inheritdoc/>
    protected override ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken) =>
        this._inner.InvokeAsync(arguments, cancellationToken);

    [Description("Fetch the html from the given url as markdown")]
    internal async Task<string> DownloadUriAsync(
        [Description("The URL to download")] string uri,
        CancellationToken cancellationToken = default)
    {
        if (!Uri.TryCreate(uri, UriKind.Absolute, out Uri? parsedUri))
        {
            return $"Error: '{uri}' is not a valid URL.";
        }

        if (parsedUri.Scheme is not "http" and not "https")
        {
            return $"Error: Only HTTP and HTTPS URLs are supported. Got: '{parsedUri.Scheme}'.";
        }

        AccessCheckResult access = await this.CheckAccessAsync(parsedUri, cancellationToken);
        if (access.Error is not null)
        {
            return access.Error;
        }

        try
        {
            // Follow redirects manually, re-checking the access policy on every hop so a permitted
            // URL cannot redirect into a blocked (private/metadata/localhost) target.
            Uri currentUri = parsedUri;
            for (int hop = 0; ; hop++)
            {
                if (hop > MaxRedirects)
                {
                    return $"Error downloading {uri}: too many redirects.";
                }

                using HttpClient httpClient = CreateHttpClient(currentUri, access.Addresses);
                using var response = await httpClient.GetAsync(
                    currentUri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);

                if (response.StatusCode is HttpStatusCode.Moved or HttpStatusCode.Found
                    or HttpStatusCode.SeeOther or HttpStatusCode.TemporaryRedirect
                    or HttpStatusCode.PermanentRedirect)
                {
                    Uri? location = response.Headers.Location;
                    if (location is null)
                    {
                        return $"Error downloading {uri}: redirect with no location.";
                    }

                    // Resolve relative redirects against the current URL, then re-check access.
                    currentUri = new Uri(currentUri, location);
                    if (currentUri.Scheme is not "http" and not "https")
                    {
                        return $"Error: redirect to unsupported scheme '{currentUri.Scheme}'.";
                    }

                    access = await this.CheckAccessAsync(currentUri, cancellationToken);
                    if (access.Error is not null)
                    {
                        return access.Error;
                    }

                    continue;
                }

                response.EnsureSuccessStatusCode();
                string html = await response.Content.ReadAsStringAsync(cancellationToken);
                return HtmlToMarkdownConverter.Convert(html);
            }
        }
        catch (HttpRequestException ex)
        {
            return $"Error downloading {uri}: {ex.Message}";
        }
    }

    /// <summary>
    /// Checks whether the given URI is permitted by the configured access policy.
    /// Returns the addresses that the HTTP connection may use, or an error message if blocked.
    /// </summary>
    private async Task<AccessCheckResult> CheckAccessAsync(
        Uri uri,
        CancellationToken cancellationToken)
    {
        string host = uri.Host;
        bool isAllowedHost = false;

        // 1. Check AllowedHosts.
        if (this._options.AllowedHosts is { Count: > 0 } allowedHosts)
        {
            foreach (string pattern in allowedHosts)
            {
                if (HostMatchesPattern(host, pattern))
                {
                    isAllowedHost = true;
                    break;
                }
            }
        }

        // 2. Short-circuit when the policy is guaranteed to block.
        if (!isAllowedHost &&
            !this._options.AllowPublicNetworks &&
            !this._options.AllowPrivateNetworks &&
            !this._options.AllowAllHosts)
        {
            return AccessCheckResult.Blocked(
                $"Error: Access to '{host}' is blocked by the current access policy. Configure WebBrowsingToolOptions to allow access.");
        }

        // 3. Resolve exactly once. The resulting addresses are also used for the socket connection.
        IPAddress[] addresses;
        try
        {
            addresses = IPAddress.TryParse(uri.IdnHost, out IPAddress? literalAddress)
                ? [literalAddress]
                : await this._resolveHostAddressesAsync(uri.IdnHost, cancellationToken);
        }
        catch (SocketException)
        {
            return AccessCheckResult.Blocked($"Error: Could not resolve host '{host}'.");
        }

        if (addresses.Length == 0)
        {
            return AccessCheckResult.Blocked($"Error: Could not resolve host '{host}'.");
        }

        IPAddress[] distinctAddresses = addresses.Distinct().ToArray();
        if (isAllowedHost || this._options.AllowAllHosts)
        {
            return AccessCheckResult.Allowed(distinctAddresses);
        }

        // Permit only addresses in enabled network classes. Mixed DNS answers cannot cause the
        // connection callback to reach an address class that the policy did not authorize.
        IPAddress[] allowedAddresses = distinctAddresses
            .Where(address =>
                IsPrivateAddress(address)
                    ? this._options.AllowPrivateNetworks
                    : this._options.AllowPublicNetworks)
            .ToArray();
        if (allowedAddresses.Length > 0)
        {
            return AccessCheckResult.Allowed(allowedAddresses);
        }

        bool hasPrivateAddress = Array.Exists(distinctAddresses, IsPrivateAddress);
        bool hasPublicAddress = Array.Exists(distinctAddresses, address => !IsPrivateAddress(address));
        string networkType = (hasPrivateAddress, hasPublicAddress) switch
        {
            (true, true) => "private/internal and public network",
            (true, false) => "private/internal network",
            _ => "public network",
        };
        return AccessCheckResult.Blocked(
            $"Error: Access to '{host}' is blocked. The host resolves to a {networkType} address and the current access policy does not permit this. " +
            "Configure WebBrowsingToolOptions to allow access.");
    }

    private static HttpClient CreateHttpClient(Uri uri, IPAddress[] addresses)
    {
        // Redirects are followed by DownloadUriAsync so each hop is re-checked. A proxy is
        // disabled because the connection callback would otherwise see the proxy endpoint and
        // could no longer pin the socket to the addresses approved by the access policy.
        var handler = new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseProxy = false,
            ConnectCallback = (context, cancellationToken) =>
                ConnectAsync(context, uri.IdnHost, uri.Port, addresses, cancellationToken),
        };
        return new HttpClient(handler);
    }

    private static async ValueTask<Stream> ConnectAsync(
        SocketsHttpConnectionContext context,
        string expectedHost,
        int expectedPort,
        IPAddress[] addresses,
        CancellationToken cancellationToken)
    {
        if (!string.Equals(
                context.DnsEndPoint.Host,
                expectedHost,
                StringComparison.OrdinalIgnoreCase) ||
            context.DnsEndPoint.Port != expectedPort)
        {
            throw new HttpRequestException(
                $"Unexpected HTTP connection destination '{context.DnsEndPoint.Host}:{context.DnsEndPoint.Port}'.");
        }

        var failures = new List<SocketException>(addresses.Length);
        foreach (IPAddress address in addresses)
        {
            Socket? socket = null;
            bool streamOwnsSocket = false;

            try
            {
                socket = new Socket(address.AddressFamily, SocketType.Stream, ProtocolType.Tcp)
                {
                    NoDelay = true,
                };
                await socket.ConnectAsync(
                    new IPEndPoint(address, expectedPort),
                    cancellationToken);
                streamOwnsSocket = true;
                return new NetworkStream(socket, ownsSocket: true);
            }
            catch (SocketException ex) when (!cancellationToken.IsCancellationRequested)
            {
                failures.Add(ex);
            }
            finally
            {
                if (!streamOwnsSocket)
                {
                    socket?.Dispose();
                }
            }
        }

        throw new HttpRequestException(
            $"Could not connect to any policy-approved address for '{expectedHost}:{expectedPort}'.",
            new AggregateException(failures));
    }

    private readonly record struct AccessCheckResult(string? Error, IPAddress[] Addresses)
    {
        public static AccessCheckResult Allowed(IPAddress[] addresses) => new(null, addresses);

        public static AccessCheckResult Blocked(string error) => new(error, []);
    }

    /// <summary>
    /// Checks whether a host matches a pattern. Supports exact match and wildcard prefix (e.g., "*.example.com").
    /// </summary>
    private static bool HostMatchesPattern(string host, string pattern)
    {
        if (string.Equals(host, pattern, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        // Wildcard prefix: "*.example.com" matches "sub.example.com" and "a.b.example.com".
        if (pattern.StartsWith("*.", StringComparison.Ordinal))
        {
            string suffix = pattern[1..]; // ".example.com"
            return host.EndsWith(suffix, StringComparison.OrdinalIgnoreCase);
        }

        return false;
    }

    /// <summary>
    /// Determines whether an IP address is private, loopback, or link-local.
    /// </summary>
    private static bool IsPrivateAddress(IPAddress address)
    {
        if (address.IsIPv4MappedToIPv6)
        {
            address = address.MapToIPv4();
        }

        if (address.Equals(IPAddress.Any) || address.Equals(IPAddress.IPv6Any))
        {
            return true;
        }

        if (IPAddress.IsLoopback(address))
        {
            return true;
        }

        if (address.AddressFamily == AddressFamily.InterNetwork)
        {
            byte[] bytes = address.GetAddressBytes();
            return bytes[0] switch
            {
                10 => true,                                          // 10.0.0.0/8
                172 => bytes[1] >= 16 && bytes[1] <= 31,             // 172.16.0.0/12
                192 => bytes[1] == 168,                              // 192.168.0.0/16
                169 => bytes[1] == 254,                              // 169.254.0.0/16 (link-local + metadata)
                _ => false
            };
        }

        if (address.AddressFamily == AddressFamily.InterNetworkV6)
        {
            // fe80::/10 (link-local) or fc00::/7 (unique local).
            byte[] bytes = address.GetAddressBytes();
            if (bytes[0] == 0xfe && (bytes[1] & 0xc0) == 0x80)
            {
                return true; // Link-local
            }

            if ((bytes[0] & 0xfe) == 0xfc)
            {
                return true; // Unique local
            }
        }

        return false;
    }

    /// <summary>
    /// A simple HTML to Markdown converter using regex-based transformations.
    /// Handles the most common HTML elements without requiring external dependencies.
    /// </summary>
    private static partial class HtmlToMarkdownConverter
    {
        public static string Convert(string html)
        {
            // Extract body content if present, otherwise use the full HTML.
            var bodyMatch = BodyRegex().Match(html);
            string content = bodyMatch.Success ? bodyMatch.Groups[1].Value : html;

            // Remove script, style, and head blocks.
            content = ScriptRegex().Replace(content, string.Empty);
            content = StyleRegex().Replace(content, string.Empty);
            content = HeadRegex().Replace(content, string.Empty);
            content = CommentRegex().Replace(content, string.Empty);

            // Convert block elements before inline elements.
            content = ConvertHeadings(content);
            content = ConvertCodeBlocks(content);
            content = ConvertBlockquotes(content);
            content = ConvertLists(content);
            content = ConvertHorizontalRules(content);

            // Convert inline elements.
            content = ConvertLinks(content);
            content = ConvertImages(content);
            content = ConvertBold(content);
            content = ConvertItalic(content);
            content = ConvertInlineCode(content);

            // Convert structural elements.
            content = ConvertParagraphs(content);
            content = ConvertLineBreaks(content);

            // Strip remaining HTML tags.
            content = StripTagsRegex().Replace(content, string.Empty);

            // Decode HTML entities.
            content = WebUtility.HtmlDecode(content);

            // Clean up excessive whitespace.
            content = ExcessiveNewlinesRegex().Replace(content, "\n\n");

            return content.Trim();
        }

        private static string ConvertHeadings(string html)
        {
            html = H1Regex().Replace(html, m => $"\n# {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            html = H2Regex().Replace(html, m => $"\n## {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            html = H3Regex().Replace(html, m => $"\n### {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            html = H4Regex().Replace(html, m => $"\n#### {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            html = H5Regex().Replace(html, m => $"\n##### {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            html = H6Regex().Replace(html, m => $"\n###### {StripInnerTags(m.Groups[1].Value).Trim()}\n");
            return html;
        }

        private static string ConvertLinks(string html) =>
            LinkRegex().Replace(html, m =>
            {
                string href = m.Groups[1].Value;
                string text = StripInnerTags(m.Groups[2].Value).Trim();

                // Skip javascript and data links.
                if (href.StartsWith("javascript:", StringComparison.OrdinalIgnoreCase) ||
                    href.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
                {
                    return text;
                }

                return string.IsNullOrWhiteSpace(text) ? string.Empty : $"[{text}]({href})";
            });

        private static string ConvertImages(string html) =>
            ImageRegex().Replace(html, m =>
            {
                string src = m.Groups[1].Value;
                string alt = m.Groups[2].Value;

                // Truncate data URIs.
                if (src.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
                {
                    src = src.Split(',')[0] + "...";
                }

                return $"![{alt}]({src})";
            });

        private static string ConvertBold(string html) =>
            BoldRegex().Replace(html, m => $"**{m.Groups[2].Value}**");

        private static string ConvertItalic(string html) =>
            ItalicRegex().Replace(html, m => $"*{m.Groups[2].Value}*");

        private static string ConvertInlineCode(string html) =>
            InlineCodeRegex().Replace(html, m => $"`{m.Groups[1].Value}`");

        private static string ConvertCodeBlocks(string html) =>
            CodeBlockRegex().Replace(html, m => $"\n```\n{StripInnerTags(m.Groups[1].Value).Trim()}\n```\n");

        private static string ConvertBlockquotes(string html) =>
            BlockquoteRegex().Replace(html, m =>
            {
                string inner = StripInnerTags(m.Groups[1].Value).Trim();
                // Prefix each line with "> ".
                string quoted = string.Join("\n", inner.Split('\n').Select(line => $"> {line.Trim()}"));
                return $"\n{quoted}\n";
            });

        private static string ConvertLists(string html)
        {
            // Unordered lists.
            html = UlRegex().Replace(html, m =>
            {
                string items = LiRegex().Replace(m.Groups[1].Value, li => $"- {StripInnerTags(li.Groups[1].Value).Trim()}\n");
                return $"\n{items}";
            });

            // Ordered lists.
            html = OlRegex().Replace(html, m =>
            {
                int index = 1;
                string items = LiRegex().Replace(m.Groups[1].Value, li => $"{index++}. {StripInnerTags(li.Groups[1].Value).Trim()}\n");
                return $"\n{items}";
            });

            return html;
        }

        private static string ConvertHorizontalRules(string html) =>
            HrRegex().Replace(html, "\n---\n");

        private static string ConvertParagraphs(string html) =>
            ParagraphRegex().Replace(html, m => $"\n\n{m.Groups[1].Value}\n\n");

        private static string ConvertLineBreaks(string html) =>
            BrRegex().Replace(html, "\n");

        private static string StripInnerTags(string html) =>
            StripTagsRegex().Replace(html, string.Empty);

        // Source-generated regex patterns for performance and AOT compatibility.

        [GeneratedRegex(@"<body[^>]*>(.*?)</body>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex BodyRegex();

        [GeneratedRegex(@"<script[^>]*>.*?</script>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex ScriptRegex();

        [GeneratedRegex(@"<style[^>]*>.*?</style>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex StyleRegex();

        [GeneratedRegex(@"<head[^>]*>.*?</head>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex HeadRegex();

        [GeneratedRegex(@"<!--.*?-->", RegexOptions.Singleline)]
        private static partial Regex CommentRegex();

        [GeneratedRegex(@"<h1[^>]*>(.*?)</h1>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H1Regex();

        [GeneratedRegex(@"<h2[^>]*>(.*?)</h2>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H2Regex();

        [GeneratedRegex(@"<h3[^>]*>(.*?)</h3>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H3Regex();

        [GeneratedRegex(@"<h4[^>]*>(.*?)</h4>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H4Regex();

        [GeneratedRegex(@"<h5[^>]*>(.*?)</h5>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H5Regex();

        [GeneratedRegex(@"<h6[^>]*>(.*?)</h6>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex H6Regex();

        [GeneratedRegex(@"<a\s[^>]*href=[""']([^""']*)[""'][^>]*>(.*?)</a>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex LinkRegex();

        [GeneratedRegex(@"<img\s[^>]*src=[""']([^""']*)[""'][^>]*?(?:alt=[""']([^""']*)[""'])?[^>]*/?>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex ImageRegex();

        [GeneratedRegex(@"<(strong|b)\b[^>]*>(.*?)</\1>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex BoldRegex();

        [GeneratedRegex(@"<(em|i)\b[^>]*>(.*?)</\1>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex ItalicRegex();

        [GeneratedRegex(@"<code[^>]*>(.*?)</code>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex InlineCodeRegex();

        [GeneratedRegex(@"<pre[^>]*>(.*?)</pre>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex CodeBlockRegex();

        [GeneratedRegex(@"<blockquote[^>]*>(.*?)</blockquote>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex BlockquoteRegex();

        [GeneratedRegex(@"<ul[^>]*>(.*?)</ul>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex UlRegex();

        [GeneratedRegex(@"<ol[^>]*>(.*?)</ol>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex OlRegex();

        [GeneratedRegex(@"<li[^>]*>(.*?)</li>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex LiRegex();

        [GeneratedRegex(@"<hr\s*/?>", RegexOptions.IgnoreCase)]
        private static partial Regex HrRegex();

        [GeneratedRegex(@"<p[^>]*>(.*?)</p>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
        private static partial Regex ParagraphRegex();

        [GeneratedRegex(@"<br\s*/?>", RegexOptions.IgnoreCase)]
        private static partial Regex BrRegex();

        [GeneratedRegex(@"<[^>]+>")]
        private static partial Regex StripTagsRegex();

        [GeneratedRegex(@"\n{3,}")]
        private static partial Regex ExcessiveNewlinesRegex();
    }
}
