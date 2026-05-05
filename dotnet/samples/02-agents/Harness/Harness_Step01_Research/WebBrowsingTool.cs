// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// An AI function that downloads HTML pages and converts them to markdown.
/// </summary>
internal sealed partial class WebBrowsingTool : AIFunction
{
    private static readonly HttpClient s_httpClient = new();
    private readonly AIFunction _inner = AIFunctionFactory.Create(DownloadUriAsync);

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
    private static async Task<string> DownloadUriAsync(
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

        // NOTE: In production scenarios, consider also blocking requests to private/internal IP
        // ranges (e.g., 10.x.x.x, 172.16-31.x.x, 192.168.x.x, 127.0.0.1, 169.254.169.254)
        // to prevent SSRF attacks via prompt injection in web content.

        try
        {
            string html = await s_httpClient.GetStringAsync(parsedUri, cancellationToken);
            return HtmlToMarkdownConverter.Convert(html);
        }
        catch (HttpRequestException ex)
        {
            return $"Error downloading {uri}: {ex.Message}";
        }
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
