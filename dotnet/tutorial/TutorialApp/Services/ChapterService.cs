// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Markdig;

namespace TutorialApp.Services;

public record Chapter(string Slug, string Title, int Order);

public sealed class ChapterService
{
    private readonly string _contentDir;
    private readonly MarkdownPipeline _pipeline;
    private List<Chapter>? _chapters;

    public ChapterService(IWebHostEnvironment env)
    {
        _contentDir = Path.Combine(env.ContentRootPath, "content");
        _pipeline = new MarkdownPipelineBuilder()
            .UseAdvancedExtensions()
            .Build();
    }

    public IReadOnlyList<Chapter> GetChapters()
    {
        if (_chapters is not null)
            return _chapters;

        if (!Directory.Exists(_contentDir))
            return [];

        _chapters = Directory.GetFiles(_contentDir, "*.md")
            .Select(path =>
            {
                var filename = Path.GetFileNameWithoutExtension(path);
                var parts = filename.Split('-', 2);
                var order = parts.Length > 0 && int.TryParse(parts[0], out var n) ? n : 0;
                var title = parts.Length > 1
                    ? string.Join(' ', parts[1].Split('-').Select(w =>
                        w.Length > 0 ? char.ToUpper(w[0], CultureInfo.InvariantCulture) + w[1..] : w))
                    : filename;
                return new Chapter(Slug: filename, Title: title, Order: order);
            })
            .OrderBy(c => c.Order)
            .ToList();

        return _chapters;
    }

    public async Task<string> GetContentAsync(string slug)
    {
        var filePath = Path.Combine(_contentDir, slug + ".md");
        if (!File.Exists(filePath))
            return "<p>Chapter not found.</p>";

        var markdown = await File.ReadAllTextAsync(filePath).ConfigureAwait(false);
        return Markdown.ToHtml(markdown, _pipeline);
    }
}
