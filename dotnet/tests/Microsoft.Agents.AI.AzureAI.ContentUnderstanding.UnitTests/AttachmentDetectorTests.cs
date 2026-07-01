// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Phase 3 / dev plan task 3.2 — AttachmentDetector walks ChatMessage.Contents and resolves
/// media type + filename for each <see cref="DataContent"/> / <see cref="UriContent"/>.
/// </summary>
public sealed class AttachmentDetectorTests
{
    private static readonly byte[] s_pdfBytes =
    [
        0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x37, 0x0A, 0x25, 0xE2, 0xE3, 0xCF, 0xD3,
    ];

    private static readonly byte[] s_pngBytes =
    [
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00,
    ];

    [Fact]
    public void YieldsEmpty_ForMessagesWithoutSupportedContent()
    {
        ChatMessage msg = new(ChatRole.User, [new TextContent("hello")]);
        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    public void YieldsEmpty_ForEmptyMessages()
        => Assert.Empty(AttachmentDetector.Detect([]));

    [Fact]
    public void DetectsDataContent_WithExplicitMediaType()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf") { Name = "contract.pdf" };
        ChatMessage msg = new(ChatRole.User, [new TextContent("Read this"), dc]);

        DetectedAttachment[] detected = AttachmentDetector.Detect([msg]).ToArray();

        Assert.Single(detected);
        Assert.Equal("application/pdf", detected[0].ResolvedMediaType);
        Assert.Equal("contract.pdf", detected[0].Filename);
        Assert.Same(dc, detected[0].OriginalContent);
        Assert.NotNull(detected[0].Data);
        Assert.Null(detected[0].Uri);
    }

    [Fact]
    public void DetectsDataContent_FillsFilenameFromAdditionalProperties_WhenNameMissing()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "from-props.pdf" },
        };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("from-props.pdf", one.Filename);
    }

    [Fact]
    public void DetectsDataContent_SynthesizesFilename_WhenNeitherSourcePresent()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf");
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));

        Assert.StartsWith("attachment-", one.Filename);
        Assert.EndsWith(".pdf", one.Filename);
        // 12 hex chars (6 bytes) between "attachment-" and ".pdf"
        Assert.Matches("^attachment-[0-9a-f]{12}\\.pdf$", one.Filename);
    }

    [Fact]
    public void DetectsDataContent_ResniffsWhenOctetStream()
    {
        // Caller incorrectly tagged a PNG as octet-stream; sniffer must override.
        DataContent dc = new(s_pngBytes, "application/octet-stream") { Name = "icon.png" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("image/png", one.ResolvedMediaType);
    }

    [Fact]
    public void SilentlySkips_OctetStreamWithUnknownBytes()
    {
        DataContent dc = new(new byte[] { 0xDE, 0xAD, 0xBE, 0xEF }, "application/octet-stream") { Name = "blob.bin" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    public void SilentlySkips_UnsupportedMediaType()
    {
        // application/zip is not in SUPPORTED_MEDIA_TYPES — must skip.
        DataContent dc = new(new byte[] { 0x50, 0x4B, 0x03, 0x04 }, "application/zip") { Name = "bundle.zip" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    public void SilentlySkips_UriContentWithUnsupportedMediaType()
    {
        UriContent uc = new("https://example.com/data.json", "application/json");
        ChatMessage msg = new(ChatRole.User, [uc]);

        Assert.Empty(AttachmentDetector.Detect([msg]));
    }

    [Fact]
    public void DetectsUriContent_WithFilenameFromUriPath()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/files/audio/callcenter.mp3", "audio/mpeg");
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("audio/mpeg", one.ResolvedMediaType);
        Assert.Equal("callcenter.mp3", one.Filename);
        Assert.Null(one.Data);
        Assert.NotNull(one.Uri);
    }

    [Fact]
    public void DetectsUriContent_PrefersAdditionalPropertiesFilenameOverUriPath()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/files/something.dat", "audio/mpeg")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = "from-props.mp3" },
        };
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("from-props.mp3", one.Filename);
    }

    [Fact]
    public void DetectsUriContent_SynthesizesFilename_WhenUriHasNoExtension()
    {
        UriContent uc = new("https://contoso.blob.core.windows.net/api/stream", "video/mp4");
        ChatMessage msg = new(ChatRole.User, [uc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Matches("^attachment-[0-9a-f]{12}\\.mp4$", one.Filename);
    }

    [Fact]
    public void DetectsMultipleAttachments_AcrossMessages()
    {
        ChatMessage msg1 = new(ChatRole.User,
        [
            new TextContent("First"),
            new DataContent(s_pdfBytes, "application/pdf") { Name = "first.pdf" },
        ]);
        ChatMessage msg2 = new(ChatRole.User,
        [
            new UriContent("https://example.com/movie.mp4", "video/mp4"),
        ]);

        DetectedAttachment[] detected = AttachmentDetector.Detect([msg1, msg2]).ToArray();

        Assert.Equal(2, detected.Length);
        Assert.Equal("first.pdf", detected[0].Filename);
        Assert.Equal("movie.mp4", detected[1].Filename);
    }

    [Fact]
    public void ResolvedMediaType_FallsBackToSuppliedWhenSniffFails()
    {
        // Caller knows it's PDF; bytes don't (yet) carry the magic — supplied wins.
        DataContent dc = new(new byte[] { 0x01, 0x02 }, "application/pdf") { Name = "x.pdf" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal("application/pdf", one.ResolvedMediaType);
    }

    [Fact]
    // Filename is interpolated into LLM-visible markdown (AnalysisRenderer YAML front-matter "source:"
    // and per-document "indexed in vector store" notes), so control chars / newlines must be neutralized.
    public void DetectsDataContent_StripsControlCharsFromFilename()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf")
        {
            Name = "report\nignore-previous.pdf\x01",
        };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.DoesNotContain('\n', one.Filename);
        Assert.DoesNotContain('\r', one.Filename);
        Assert.DoesNotContain('\t', one.Filename);
        Assert.DoesNotContain('\x01', one.Filename);
        Assert.Equal("report ignore-previous.pdf", one.Filename);
    }

    [Fact]
    // security: path-traversal hardening — slash / backslash separators and ".." segments are removed.
    public void DetectsDataContent_StripsPathSeparatorsAndDotDot()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf")
        {
            Name = "../../etc/passwd.pdf",
        };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.DoesNotContain('/', one.Filename);
        Assert.DoesNotContain('\\', one.Filename);
        Assert.DoesNotContain("..", one.Filename);
        Assert.Equal("etc passwd.pdf", one.Filename);
    }

    [Fact]
    // security: cap filename length at 255 chars so a hostile caller can't pad context with a huge name.
    public void DetectsDataContent_CapsFilenameAt255Characters()
    {
        string huge = new string('a', 1000) + ".pdf";
        DataContent dc = new(s_pdfBytes, "application/pdf") { Name = huge };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Equal(255, one.Filename.Length);
    }

    [Fact]
    // security: when sanitization removes everything (filename was *only* control chars / separators),
    // fall back to the content-hash synthesizer rather than emitting an empty key.
    public void DetectsDataContent_FallsBackToSynthesize_WhenSanitizedFilenameEmpty()
    {
        DataContent dc = new(s_pdfBytes, "application/pdf") { Name = "\x01\x02\x03" };
        ChatMessage msg = new(ChatRole.User, [dc]);

        DetectedAttachment one = Assert.Single(AttachmentDetector.Detect([msg]));
        Assert.Matches("^attachment-[0-9a-f]{12}\\.pdf$", one.Filename);
    }
}
