// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI;

internal sealed record GitignoreRule(string Base, Regex Regex, bool Negate, bool DirectoryOnly, int Order);

/// <summary>
/// Loads and applies <c>.gitignore</c> rules across a directory tree. Used by file-system
/// discovery operations to filter out version-control-ignored entries.
/// </summary>
internal sealed class GitignoreMatcher
{
    private readonly IReadOnlyList<GitignoreRule> _rules;

    private GitignoreMatcher(IReadOnlyList<GitignoreRule> rules) => this._rules = rules;

    internal static GitignoreMatcher Load(string root)
    {
        var rules = new List<GitignoreRule>();
        int order = 0;
        foreach (string file in Directory.EnumerateFiles(root, ".gitignore", SearchOption.AllDirectories).Where(f => !f.Replace('\\', '/').Contains("/.git/")))
        {
            string relDir = Path.GetDirectoryName(FileSystemTool.GetRelativePath(root, file))?.Replace('\\', '/') ?? string.Empty;
            if (relDir == ".") { relDir = string.Empty; }
            rules.AddRange(Compile(File.ReadAllText(file), relDir, ref order));
        }
        return new GitignoreMatcher(rules);
    }

    internal bool IsIgnored(string relativePosixPath, bool isDirectory)
    {
        bool ignored = false;
        foreach (GitignoreRule rule in this._rules)
        {
            if (rule.DirectoryOnly && !isDirectory) { continue; }
            if (rule.Regex.IsMatch(relativePosixPath)) { ignored = !rule.Negate; }
        }
        return ignored;
    }

    private static List<GitignoreRule> Compile(string text, string basePath, ref int order)
    {
        var rules = new List<GitignoreRule>();
        var trailingWhitespace = new Regex(@"(?<!\\)\s+$", RegexOptions.None, TimeSpan.FromSeconds(1));
        foreach (string raw in text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            string line = trailingWhitespace.Replace(raw, string.Empty);
            if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) { continue; }
            bool negate = line.StartsWith("!", StringComparison.Ordinal);
            if (negate) { line = line.Substring(1); }
            line = line.Replace("\\#", "#").Replace("\\!", "!");
            bool dirOnly = line.EndsWith("/", StringComparison.Ordinal);
            if (dirOnly) { line = line.TrimEnd('/'); }
            bool anchored = line.StartsWith("/", StringComparison.Ordinal);
            if (anchored) { line = line.Substring(1); }
            bool containsSlash = line.IndexOf('/') >= 0;
            string body = GitignorePatternToRegex(line, anchored || containsSlash);
            string prefix = !string.IsNullOrEmpty(basePath) ? "^" + Regex.Escape(basePath) + "/" : "^";
            if (!anchored && !containsSlash) { prefix += "(?:.*/)?"; }
            string suffix = dirOnly ? "(?:/.*)?$" : "$";
            rules.Add(new GitignoreRule(basePath, new Regex(prefix + body + suffix, RegexOptions.Compiled), negate, dirOnly, order++));
        }

        return rules;
    }

    private static string GitignorePatternToRegex(string pattern, bool full) => full ? FileSystemTool.GlobToRegex(pattern).Trim('^', '$') : FnmatchForGitignore(pattern);

    private static string FnmatchForGitignore(string pattern)
    {
        var sb = new StringBuilder();
        foreach (char ch in pattern)
        {
            if (ch == '*') { sb.Append("[^/]*"); }
            else if (ch == '?') { sb.Append("[^/]"); }
            else { sb.Append(Regex.Escape(ch.ToString())); }
        }
        return sb.ToString();
    }
}
