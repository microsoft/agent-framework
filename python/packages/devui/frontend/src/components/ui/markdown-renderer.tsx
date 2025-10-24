/**
 * Lightweight Markdown Renderer
 *
 * A minimal markdown renderer with zero dependencies for rendering LLM responses.
 * Handles the most common markdown patterns without bloating bundle size.
 *
 * Supported syntax:
 * - **bold** and __bold__
 * - *italic* and _italic_
 * - `inline code`
 * - ```code blocks``` (with copy button on hover)
 * - [links](url)
 * - **[bold links](url)** and *[italic links](url)*
 * - # Headers (H1-H6)
 * - Lists (ordered and unordered)
 * - > Blockquotes
 * - Tables (| col1 | col2 |)
 * - Horizontal rules (---)
 */

import React, { useState, useRef, useEffect } from "react";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

interface CodeBlockProps {
  code: string;
  language?: string;
}

/**
 * Code block component with copy button
 */
function CodeBlock({ code, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);

      // Clear any existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      // Set new timeout and store reference
      timeoutRef.current = setTimeout(() => {
        setCopied(false);
        timeoutRef.current = null;
      }, 2000);
    } catch (err) {
      console.error("Failed to copy code:", err);
    }
  };

  return (
    <div className="relative group">
      <pre className="my-3 p-3 bg-foreground/5 dark:bg-foreground/10 rounded overflow-x-auto border border-foreground/10">
        <code className="text-xs font-mono block whitespace-pre-wrap break-words">
          {language && (
            <span className="opacity-60 text-[10px] mb-1 block uppercase">
              {language}
            </span>
          )}
          {code}
        </code>
      </pre>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-md border shadow-sm
                   bg-background hover:bg-accent
                   text-muted-foreground hover:text-foreground
                   transition-all duration-200
                   opacity-0 group-hover:opacity-100"
        title={copied ? "Copied!" : "Copy code"}
      >
        {copied ? (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-green-600 dark:text-green-400"
          >
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        )}
      </button>
    </div>
  );
}

/**
 * Parse markdown text into React elements
 */
export function MarkdownRenderer({
  content,
  className = "",
}: MarkdownRendererProps) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code blocks (multiline)
    if (line.trim().startsWith("```")) {
      const codeLines: string[] = [];
      const langMatch = line.trim().match(/^```(\w+)?/);
      const language = langMatch?.[1] || "";
      i++; // Skip opening ```

      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // Skip closing ```

      elements.push(
        <CodeBlock
          key={elements.length}
          code={codeLines.join("\n")}
          language={language}
        />
      );
      continue;
    }

    // Headers
    const headerMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headerMatch) {
      const level = headerMatch[1].length;
      const text = headerMatch[2];
      const sizes = [
        "text-2xl",
        "text-xl",
        "text-lg",
        "text-base",
        "text-sm",
        "text-sm",
      ];
      const className = `${
        sizes[level - 1]
      } font-semibold mt-4 mb-2 first:mt-0 break-words`;

      // Render appropriate header level
      const header =
        level === 1 ? (
          <h1 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h1>
        ) : level === 2 ? (
          <h2 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h2>
        ) : level === 3 ? (
          <h3 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h3>
        ) : level === 4 ? (
          <h4 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h4>
        ) : level === 5 ? (
          <h5 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h5>
        ) : (
          <h6 key={elements.length} className={className}>
            {parseInlineMarkdown(text)}
          </h6>
        );

      elements.push(header);
      i++;
      continue;
    }

    // Unordered lists
    if (line.match(/^[\s]*[-*+]\s+/)) {
      const listItems: string[] = [];

      while (i < lines.length && lines[i].match(/^[\s]*[-*+]\s+/)) {
        const itemText = lines[i].replace(/^[\s]*[-*+]\s+/, "");
        listItems.push(itemText);
        i++;
      }

      elements.push(
        <ul
          key={elements.length}
          className="my-2 ml-4 list-disc space-y-1 break-words"
        >
          {listItems.map((item, idx) => (
            <li key={idx} className="text-sm break-words">
              {parseInlineMarkdown(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Ordered lists
    if (line.match(/^[\s]*\d+\.\s+/)) {
      const listItems: string[] = [];

      while (i < lines.length && lines[i].match(/^[\s]*\d+\.\s+/)) {
        const itemText = lines[i].replace(/^[\s]*\d+\.\s+/, "");
        listItems.push(itemText);
        i++;
      }

      elements.push(
        <ol
          key={elements.length}
          className="my-2 ml-4 list-decimal space-y-1 break-words"
        >
          {listItems.map((item, idx) => (
            <li key={idx} className="text-sm break-words">
              {parseInlineMarkdown(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // Tables
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = [];

      // Collect all table lines
      while (
        i < lines.length &&
        lines[i].trim().startsWith("|") &&
        lines[i].trim().endsWith("|")
      ) {
        tableLines.push(lines[i].trim());
        i++;
      }

      // Parse table (need at least 2 lines: header + separator)
      if (tableLines.length >= 2) {
        const headerCells = tableLines[0]
          .split("|")
          .slice(1, -1)
          .map((cell) => cell.trim());

        // Check if second line is a separator (contains dashes)
        const isSeparator = tableLines[1].match(/^\|[\s\-:|]+\|$/);

        if (isSeparator) {
          const bodyRows = tableLines.slice(2).map((row) =>
            row
              .split("|")
              .slice(1, -1)
              .map((cell) => cell.trim())
          );

          elements.push(
            <div key={elements.length} className="my-3 overflow-x-auto">
              <table className="min-w-full border border-foreground/10 text-sm">
                <thead className="bg-foreground/5">
                  <tr>
                    {headerCells.map((header, idx) => (
                      <th
                        key={idx}
                        className="border-b border-foreground/10 px-3 py-2 text-left font-semibold break-words"
                      >
                        {parseInlineMarkdown(header)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bodyRows.map((row, rowIdx) => (
                    <tr
                      key={rowIdx}
                      className="border-b border-foreground/5 last:border-b-0"
                    >
                      {row.map((cell, cellIdx) => (
                        <td
                          key={cellIdx}
                          className="px-3 py-2 border-r border-foreground/5 last:border-r-0 break-words"
                        >
                          {parseInlineMarkdown(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
          continue;
        }
      }

      // Not a valid table, render as regular paragraphs
      for (const tableLine of tableLines) {
        elements.push(
          <p key={elements.length} className="my-1">
            {parseInlineMarkdown(tableLine)}
          </p>
        );
      }
      continue;
    }

    // Blockquotes
    if (line.trim().startsWith(">")) {
      const quoteLines: string[] = [];

      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }

      elements.push(
        <blockquote
          key={elements.length}
          className="my-2 pl-4 border-l-4 border-current/30 opacity-80 italic break-words"
        >
          {quoteLines.map((quoteLine, idx) => (
            <div key={idx} className="break-words">
              {parseInlineMarkdown(quoteLine)}
            </div>
          ))}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (line.match(/^[\s]*[-*_]{3,}[\s]*$/)) {
      elements.push(
        <hr key={elements.length} className="my-4 border-t border-border" />
      );
      i++;
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      elements.push(<div key={elements.length} className="h-2" />);
      i++;
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={elements.length} className="my-1 break-words">
        {parseInlineMarkdown(line)}
      </p>
    );
    i++;
  }

  return (
    <div className={`markdown-content break-words ${className}`}>
      {elements}
    </div>
  );
}

/**
 * Parse inline markdown patterns (bold, italic, code, links)
 */
function parseInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  // Pattern priority: code > bold > italic > links
  // This prevents conflicts between overlapping patterns

  while (remaining.length > 0) {
    // Inline code (highest priority to avoid parsing inside code)
    const codeMatch = remaining.match(/`([^`]+)`/);
    if (codeMatch && codeMatch.index !== undefined) {
      // Add text before code
      if (codeMatch.index > 0) {
        parts.push(
          <span key={key++}>
            {parseBoldItalicLinks(remaining.slice(0, codeMatch.index))}
          </span>
        );
      }

      // Add code
      parts.push(
        <code
          key={key++}
          className="px-1.5 py-0.5 bg-foreground/10 rounded text-xs font-mono border border-foreground/20"
        >
          {codeMatch[1]}
        </code>
      );

      remaining = remaining.slice(codeMatch.index + codeMatch[0].length);
      continue;
    }

    // No more special patterns, parse remaining text for bold/italic/links
    parts.push(<span key={key++}>{parseBoldItalicLinks(remaining)}</span>);
    break;
  }

  return parts;
}

/**
 * Parse bold, italic, and links (after code has been extracted)
 */
function parseBoldItalicLinks(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    // Try to match patterns in order
    // IMPORTANT: Handle **[link](url)** pattern first (bold markers around link)
    const patterns = [
      { regex: /\*\*\[([^\]]+)\]\(([^)]+)\)\*\*/, component: "strong-link" }, // **[text](url)**
      { regex: /__\[([^\]]+)\]\(([^)]+)\)__/, component: "strong-link" }, // __[text](url)__
      { regex: /\*\[([^\]]+)\]\(([^)]+)\)\*/, component: "em-link" }, // *[text](url)*
      { regex: /_\[([^\]]+)\]\(([^)]+)\)_/, component: "em-link" }, // _[text](url)_
      { regex: /\[([^\]]+)\]\(([^)]+)\)/, component: "link" }, // [text](url)
      { regex: /\*\*(.+?)\*\*/, component: "strong" }, // **bold**
      { regex: /__(.+?)__/, component: "strong" }, // __bold__
      { regex: /\*(.+?)\*/, component: "em" }, // *italic*
      { regex: /_(.+?)_/, component: "em" }, // _italic_
    ];

    let matched = false;

    for (const pattern of patterns) {
      const match = remaining.match(pattern.regex);

      if (match && match.index !== undefined) {
        // Add text before match
        if (match.index > 0) {
          parts.push(remaining.slice(0, match.index));
        }

        // Add matched element
        if (pattern.component === "strong") {
          parts.push(
            <strong key={key++} className="font-semibold">
              {match[1]}
            </strong>
          );
        } else if (pattern.component === "em") {
          parts.push(
            <em key={key++} className="italic">
              {match[1]}
            </em>
          );
        } else if (pattern.component === "strong-link") {
          // **[text](url)** - Bold link
          const linkText = match[1];
          const linkUrl = match[2];
          const formattedLinkText = parseBoldItalicLinks(linkText);

          parts.push(
            <strong key={key++} className="font-semibold">
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline break-words"
              >
                {formattedLinkText}
              </a>
            </strong>
          );
        } else if (pattern.component === "em-link") {
          // *[text](url)* - Italic link
          const linkText = match[1];
          const linkUrl = match[2];
          const formattedLinkText = parseBoldItalicLinks(linkText);

          parts.push(
            <em key={key++} className="italic">
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline break-words"
              >
                {formattedLinkText}
              </a>
            </em>
          );
        } else if (pattern.component === "link") {
          // [text](url) - Regular link
          const linkText = match[1];
          const linkUrl = match[2];
          const formattedLinkText = parseBoldItalicLinks(linkText);

          parts.push(
            <a
              key={key++}
              href={linkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline break-words"
            >
              {formattedLinkText}
            </a>
          );
        }

        remaining = remaining.slice(match.index + match[0].length);
        matched = true;
        break;
      }
    }

    // No pattern matched, add remaining text and exit
    if (!matched) {
      if (remaining.length > 0) {
        parts.push(remaining);
      }
      break;
    }
  }

  return parts;
}
