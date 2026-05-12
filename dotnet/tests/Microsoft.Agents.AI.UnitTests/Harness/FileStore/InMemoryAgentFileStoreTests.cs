// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

public class InMemoryAgentFileStoreTests
{
    [Fact]
    public async Task WriteAndReadFile_ReturnsContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act
        await store.WriteFileAsync("notes.md", "Hello world");
        var content = await store.ReadFileAsync("notes.md");

        // Assert
        Assert.Equal("Hello world", content);
    }

    [Fact]
    public async Task ReadFile_NonExistent_ReturnsNullAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act
        var content = await store.ReadFileAsync("nonexistent.md");

        // Assert
        Assert.Null(content);
    }

    [Fact]
    public async Task WriteFile_OverwritesExistingAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Original");

        // Act
        await store.WriteFileAsync("notes.md", "Updated");
        var content = await store.ReadFileAsync("notes.md");

        // Assert
        Assert.Equal("Updated", content);
    }

    [Fact]
    public async Task DeleteFile_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");

        // Act
        var deleted = await store.DeleteFileAsync("notes.md");

        // Assert
        Assert.True(deleted);
        Assert.Null(await store.ReadFileAsync("notes.md"));
    }

    [Fact]
    public async Task DeleteFile_NonExistent_ReturnsFalseAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act
        var deleted = await store.DeleteFileAsync("nonexistent.md");

        // Assert
        Assert.False(deleted);
    }

    [Fact]
    public async Task ListFiles_ReturnsDirectChildrenAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/file1.md", "Content 1");
        await store.WriteFileAsync("folder/file2.md", "Content 2");
        await store.WriteFileAsync("folder/sub/file3.md", "Content 3");
        await store.WriteFileAsync("other/file4.md", "Content 4");

        // Act
        var files = await store.ListFilesAsync("folder");

        // Assert
        Assert.Equal(2, files.Count);
        Assert.Contains("file1.md", files);
        Assert.Contains("file2.md", files);
    }

    [Fact]
    public async Task ListFiles_EmptyDirectory_ReturnsEmptyAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act
        var files = await store.ListFilesAsync("empty");

        // Assert
        Assert.Empty(files);
    }

    [Fact]
    public async Task ListFiles_RootDirectory_ReturnsRootFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("root.md", "Content");
        await store.WriteFileAsync("folder/nested.md", "Content");

        // Act
        var files = await store.ListFilesAsync("");

        // Assert
        Assert.Single(files);
        Assert.Equal("root.md", files[0]);
    }

    [Fact]
    public async Task ListFiles_IncludesDescriptionFilesAsync()
    {
        // Arrange — the store is dumb; it returns all files including _description.md
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Content");
        await store.WriteFileAsync("folder/notes_description.md", "Desc");

        // Act
        var files = await store.ListFilesAsync("folder");

        // Assert
        Assert.Equal(2, files.Count);
        Assert.Contains("notes.md", files);
        Assert.Contains("notes_description.md", files);
    }

    [Fact]
    public async Task FileExists_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("notes.md", "Content");

        // Act & Assert
        Assert.True(await store.FileExistsAsync("notes.md"));
    }

    [Fact]
    public async Task FileExists_NonExistent_ReturnsFalseAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        Assert.False(await store.FileExistsAsync("nonexistent.md"));
    }

    [Fact]
    public async Task SearchFiles_FindsMatchingContentAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "The quick brown fox jumps over the lazy dog");
        await store.WriteFileAsync("folder/other.md", "No match here");

        // Act
        var results = await store.SearchFilesAsync("folder", "brown fox");

        // Assert
        Assert.Single(results);
        Assert.Equal("notes.md", results[0].FileName);
        Assert.Contains("brown fox", results[0].Snippet);
    }

    [Fact]
    public async Task SearchFiles_ReturnsMatchingLineNumbersAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Line one\nLine two with match\nLine three\nLine four with match");

        // Act
        var results = await store.SearchFilesAsync("folder", "match");

        // Assert
        Assert.Single(results);
        Assert.Equal(2, results[0].MatchingLines.Count);
        Assert.Equal(2, results[0].MatchingLines[0].LineNumber);
        Assert.Equal("Line two with match", results[0].MatchingLines[0].Line);
        Assert.Equal(4, results[0].MatchingLines[1].LineNumber);
        Assert.Equal("Line four with match", results[0].MatchingLines[1].Line);
    }

    [Fact]
    public async Task SearchFiles_CaseInsensitiveAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Important Data Here");

        // Act
        var results = await store.SearchFilesAsync("folder", "important data");

        // Assert
        Assert.Single(results);
    }

    [Fact]
    public async Task SearchFiles_SupportsRegexPatternAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Error: something went wrong\nWarning: check this\nInfo: all good");

        // Act
        var results = await store.SearchFilesAsync("folder", "error|warning");

        // Assert
        Assert.Single(results);
        Assert.Equal(2, results[0].MatchingLines.Count);
        Assert.Equal(1, results[0].MatchingLines[0].LineNumber);
        Assert.Equal(2, results[0].MatchingLines[1].LineNumber);
    }

    [Fact]
    public async Task SearchFiles_SupportsRegexWithSpecialCharactersAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/code.cs", "var x = 42;\nvar y = 100;\nconst z = 7;");

        // Act — regex matching lines starting with "var"
        var results = await store.SearchFilesAsync("folder", @"^var\b");

        // Assert
        Assert.Single(results);
        Assert.Equal(2, results[0].MatchingLines.Count);
    }

    [Fact]
    public async Task SearchFiles_WithGlobPattern_FiltersFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Important data");
        await store.WriteFileAsync("folder/data.txt", "Important data");
        await store.WriteFileAsync("folder/code.cs", "Important data");

        // Act — only search markdown files
        var results = await store.SearchFilesAsync("folder", "Important", filePattern: "*.md");

        // Assert
        Assert.Single(results);
        Assert.Equal("notes.md", results[0].FileName);
    }

    [Fact]
    public async Task SearchFiles_WithGlobPattern_MultipleExtensionsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "match here");
        await store.WriteFileAsync("folder/data.txt", "match here");
        await store.WriteFileAsync("folder/code.cs", "match here");

        // Act — search both md and txt files
        var resultsMd = await store.SearchFilesAsync("folder", "match", filePattern: "*.md");
        var resultsTxt = await store.SearchFilesAsync("folder", "match", filePattern: "*.txt");

        // Assert
        Assert.Single(resultsMd);
        Assert.Equal("notes.md", resultsMd[0].FileName);
        Assert.Single(resultsTxt);
        Assert.Equal("data.txt", resultsTxt[0].FileName);
    }

    [Fact]
    public async Task SearchFiles_WithGlobPattern_PrefixMatchAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/research_ai.md", "findings");
        await store.WriteFileAsync("folder/research_ml.md", "findings");
        await store.WriteFileAsync("folder/notes.md", "findings");

        // Act
        var results = await store.SearchFilesAsync("folder", "findings", filePattern: "research*");

        // Assert
        Assert.Equal(2, results.Count);
        Assert.All(results, r => Assert.StartsWith("research", r.FileName));
    }

    [Fact]
    public async Task SearchFiles_WithNullGlobPattern_SearchesAllFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "match");
        await store.WriteFileAsync("folder/data.txt", "match");

        // Act
        var results = await store.SearchFilesAsync("folder", "match", filePattern: null);

        // Assert
        Assert.Equal(2, results.Count);
    }

    [Fact]
    public async Task SearchFiles_NoMatch_ReturnsEmptyAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Some content");

        // Act
        var results = await store.SearchFilesAsync("folder", "nonexistent query");

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task SearchFiles_IgnoresSubdirectoryFilesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();
        await store.WriteFileAsync("folder/notes.md", "Match here");
        await store.WriteFileAsync("folder/sub/deep.md", "Match here too");

        // Act
        var results = await store.SearchFilesAsync("folder", "Match");

        // Assert
        Assert.Single(results);
        Assert.Equal("notes.md", results[0].FileName);
    }

    [Fact]
    public async Task SearchFiles_Snippet_IncludesSurroundingContextAsync()
    {
        // Arrange — place the match in the middle of a long line so ±50 chars are available.
        var store = new InMemoryAgentFileStore();
        string padding = new('A', 60);
        string content = $"{padding}MATCH_HERE{padding}";
        await store.WriteFileAsync("folder/file.md", content);

        // Act
        var results = await store.SearchFilesAsync("folder", "MATCH_HERE");

        // Assert — snippet should contain the match and surrounding context (up to ±50 chars).
        Assert.Single(results);
        string snippet = results[0].Snippet;
        Assert.Contains("MATCH_HERE", snippet);
        Assert.True(snippet.Length <= 50 + "MATCH_HERE".Length + 50, "Snippet should be at most ±50 chars around the match.");
        Assert.True(snippet.Length > "MATCH_HERE".Length, "Snippet should include surrounding context.");
    }

    [Fact]
    public async Task SearchFiles_Snippet_MatchNearStartOfFileAsync()
    {
        // Arrange — match is at the very beginning, so no leading context is available.
        var store = new InMemoryAgentFileStore();
        string trailing = new('B', 80);
        string content = $"MATCH{trailing}";
        await store.WriteFileAsync("folder/file.md", content);

        // Act
        var results = await store.SearchFilesAsync("folder", "MATCH");

        // Assert — snippet should start at the beginning of the file.
        Assert.Single(results);
        Assert.StartsWith("MATCH", results[0].Snippet);
        Assert.True(results[0].Snippet.Length <= "MATCH".Length + 50);
    }

    [Fact]
    public async Task SearchFiles_Snippet_MatchNearEndOfFileAsync()
    {
        // Arrange — match is at the very end, so no trailing context is available.
        var store = new InMemoryAgentFileStore();
        string leading = new('C', 80);
        string content = $"{leading}MATCH";
        await store.WriteFileAsync("folder/file.md", content);

        // Act
        var results = await store.SearchFilesAsync("folder", "MATCH");

        // Assert — snippet should end at the end of the file.
        Assert.Single(results);
        Assert.EndsWith("MATCH", results[0].Snippet);
        Assert.True(results[0].Snippet.Length <= 50 + "MATCH".Length);
    }

    [Fact]
    public async Task SearchFiles_Snippet_UsesFirstMatchPositionAsync()
    {
        // Arrange — "target" appears on lines 1 and 3, but the regex only matches line 3
        // because we require the word "UNIQUE" which only appears on line 3.
        var store = new InMemoryAgentFileStore();
        const string Content = "Line one has some text\nLine two is filler\nLine three has UNIQUE_MARKER here";
        await store.WriteFileAsync("folder/file.md", Content);

        // Act
        var results = await store.SearchFilesAsync("folder", "UNIQUE_MARKER");

        // Assert — snippet should be from around line 3, not line 1.
        Assert.Single(results);
        Assert.Contains("UNIQUE_MARKER", results[0].Snippet);
        Assert.Contains("Line three", results[0].Snippet);
    }

    [Fact]
    public async Task SearchFiles_Snippet_CorrectForMultiLineMatchAsync()
    {
        // Arrange — match is on the second line with enough distance from line 1
        // that the ±50 char snippet window does not reach the start of the file.
        var store = new InMemoryAgentFileStore();
        string line1 = new('X', 100);
        string line2 = new string('Y', 60) + "FIND_ME" + new string('Z', 60);
        string line3 = new('W', 100);
        string content = $"{line1}\n{line2}\n{line3}";
        await store.WriteFileAsync("folder/file.md", content);

        // Act
        var results = await store.SearchFilesAsync("folder", "FIND_ME");

        // Assert — snippet should contain the match from line 2.
        Assert.Single(results);
        Assert.Contains("FIND_ME", results[0].Snippet);

        // The match is at offset 101 (line1=100 + '\n') + 60 = 161.
        // snippetStart = 161 - 50 = 111, which is well past line 1 (ends at offset 100).
        // So line 1 content should not appear in the snippet.
        Assert.DoesNotContain("XXXX", results[0].Snippet);
    }

    [Fact]
    public async Task PathNormalization_HandlesBackslashesAndTrailingSlashesAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act
        await store.WriteFileAsync("folder\\file.md", "Content");
        var content = await store.ReadFileAsync("folder/file.md");

        // Assert
        Assert.Equal("Content", content);
    }

    [Fact]
    public async Task WriteFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.WriteFileAsync("../escape.md", "Content"));
    }

    [Fact]
    public async Task ReadFile_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.ReadFileAsync("folder/../../escape.md"));
    }

    [Fact]
    public async Task WriteFile_AbsolutePath_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.WriteFileAsync("/etc/passwd", "Content"));
    }

    [Fact]
    public async Task WriteFile_DoubleDotsInFileName_AllowedAsync()
    {
        // Arrange — "notes..md" contains ".." as a substring but not as a path segment.
        var store = new InMemoryAgentFileStore();

        // Act
        await store.WriteFileAsync("notes..md", "Content");
        var content = await store.ReadFileAsync("notes..md");

        // Assert
        Assert.Equal("Content", content);
    }

    [Fact]
    public async Task WriteFile_DriveRootedPath_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.WriteFileAsync("C:\\temp\\file.md", "Content"));
    }

    [Fact]
    public async Task ListFiles_PathTraversal_ThrowsAsync()
    {
        // Arrange
        var store = new InMemoryAgentFileStore();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => store.ListFilesAsync("../other"));
    }
}
