// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Markdig;

namespace TutorialApp.Services;

public record Chapter(string Slug, string Title, int Order);

public sealed class ChapterService
{
    private readonly string _contentRoot;
    private readonly MarkdownPipeline _pipeline;
    private readonly Dictionary<string, List<Chapter>> _cache = [];

    public ChapterService(IWebHostEnvironment env)
    {
        // Content files are copied to the output directory via CopyToOutputDirectory=Always.
        // AppContext.BaseDirectory is the output directory (bin/Debug/net10.0/), which is
        // where the markdown files live at runtime — unlike ContentRootPath (the project dir).
        _contentRoot = Path.Combine(AppContext.BaseDirectory, "content");
        _pipeline = new MarkdownPipelineBuilder()
            .UseAdvancedExtensions()
            .Build();
    }

    public IReadOnlyList<Chapter> GetChapters(string lang = "en")
    {
        if (_cache.TryGetValue(lang, out var cached))
            return cached;

        var dir = Path.Combine(_contentRoot, lang);
        if (!Directory.Exists(dir))
            dir = Path.Combine(_contentRoot, "en"); // fallback

        if (!Directory.Exists(dir))
            return [];

        var chapters = Directory.GetFiles(dir, "*.md")
            .Select(path =>
            {
                var filename = Path.GetFileNameWithoutExtension(path);
                var parts = filename.Split('-', 2);
                var order = parts.Length > 0 && int.TryParse(parts[0], out var n) ? n : 0;
                var title = ExtractH1Title(path)
                    ?? (parts.Length > 1
                        ? string.Join(' ', parts[1].Split('-').Select(w =>
                            w.Length > 0 ? char.ToUpper(w[0], CultureInfo.InvariantCulture) + w[1..] : w))
                        : filename);
                return new Chapter(Slug: filename, Title: title, Order: order);
            })
            .OrderBy(c => c.Order)
            .ToList();

        _cache[lang] = chapters;
        return chapters;
    }

    public async Task<string> GetContentAsync(string slug, string lang = "en")
    {
        var path = Path.Combine(_contentRoot, lang, slug + ".md");
        if (!File.Exists(path))
            path = Path.Combine(_contentRoot, "en", slug + ".md"); // fallback
        if (!File.Exists(path))
            return "<p>Chapter not found.</p>";

        var markdown = await File.ReadAllTextAsync(path).ConfigureAwait(false);
        return Markdown.ToHtml(markdown, _pipeline);
    }

    private static string? ExtractH1Title(string filePath)
    {
        foreach (var line in File.ReadLines(filePath))
        {
            if (line.StartsWith("# ", StringComparison.Ordinal))
                return line[2..].Trim();
            if (line.Length > 0) // stop at first non-blank, non-H1 line
                break;
        }
        return null;
    }
}
