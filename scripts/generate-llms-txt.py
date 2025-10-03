#!/usr/bin/env python3
"""
Generate llms.txt file by combining all Markdown files in the repository.
This script creates a comprehensive sitemap for AI systems to understand the project structure.
"""

import os
import re
from pathlib import Path
from typing import List
from datetime import datetime


def get_file_priority(file_path: str) -> int:
    """
    Assign priority to files based on their importance for AI understanding.
    Lower numbers = higher priority.
    """
    file_name = os.path.basename(file_path).lower()
    dir_path = os.path.dirname(file_path).lower()

    # Root level important files
    if file_name == "readme.md" and "/" not in file_path.replace("\\", "/"):
        return 1

    # Getting started and user guides
    if "getting-started" in dir_path or "getting_started" in dir_path:
        return 2
    if "user-guide" in dir_path or "user_guide" in dir_path:
        return 3

    # Language-specific READMEs
    if file_name == "readme.md" and ("python" in dir_path or "dotnet" in dir_path):
        return 4

    # Documentation files
    if "docs" in dir_path:
        if "faqs" in file_name or "contributing" in file_name:
            return 5
        return 6

    # Specs and design documents
    if "specs" in dir_path or "design" in dir_path:
        return 7

    # Samples and examples
    if "samples" in dir_path or "examples" in dir_path:
        return 8

    # Contributing and support files
    if any(
        keyword in file_name
        for keyword in ["contributing", "support", "security", "code_of_conduct"]
    ):
        return 9

    # Everything else
    return 10


def clean_content(content: str) -> str:
    """Clean and normalize markdown content."""
    # Remove excessive whitespace
    content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)
    # Remove trailing whitespace
    content = "\n".join(line.rstrip() for line in content.split("\n"))
    # Ensure content ends with a newline
    content = content.strip() + "\n"
    return content


def extract_title_from_content(content: str, file_path: str) -> str:
    """Extract title from markdown content or use filename."""
    lines = content.strip().split("\n")
    for line in lines:
        if line.startswith("# "):
            return line[2:].strip()

    # Fallback to filename
    return (
        os.path.splitext(os.path.basename(file_path))[0]
        .replace("_", " ")
        .replace("-", " ")
        .title()
    )


def get_markdown_files(root_dir: str) -> List[str]:
    """Get all markdown files in the repository."""
    markdown_files = []
    root_path = Path(root_dir)

    for md_file in root_path.rglob("*.md"):
        # Skip files in .git, node_modules, and other common ignored directories
        if any(part.startswith(".") for part in md_file.parts):
            continue
        if any(
            ignored in str(md_file).lower()
            for ignored in ["node_modules", "__pycache__", ".git"]
        ):
            continue

        markdown_files.append(str(md_file.relative_to(root_path)))

    return markdown_files


def generate_llms_txt(root_dir: str = ".") -> str:
    """Generate the llms.txt content."""
    markdown_files = get_markdown_files(root_dir)

    # Sort files by priority and then alphabetically
    sorted_files = sorted(
        markdown_files, key=lambda x: (get_file_priority(x), x.lower())
    )

    # Build the llms.txt content
    llms_content = []

    # Header
    llms_content.append("# Microsoft Agent Framework - AI Sitemap")
    llms_content.append("")
    llms_content.append(
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    llms_content.append("")
    llms_content.append(
        "This file serves as a comprehensive sitemap for AI systems to understand the Microsoft Agent Framework project."
    )
    llms_content.append(
        "It combines all Markdown documentation in the repository, organized by importance and category."
    )
    llms_content.append("")
    llms_content.append("## Overview")
    llms_content.append("")
    llms_content.append(
        "Microsoft Agent Framework is a comprehensive multi-language framework for building, orchestrating, and deploying AI agents with support for both .NET and Python implementations."
    )
    llms_content.append("")
    llms_content.append("## Table of Contents")
    llms_content.append("")

    # Generate TOC
    current_priority = None
    section_names = {
        1: "Project Overview",
        2: "Getting Started",
        3: "User Guides",
        4: "Language-Specific Documentation",
        5: "General Documentation",
        6: "Technical Documentation",
        7: "Specifications and Design",
        8: "Examples and Samples",
        9: "Contributing and Support",
        10: "Additional Resources",
    }

    toc_entries = []
    for file_path in sorted_files:
        priority = get_file_priority(file_path)
        if priority != current_priority:
            if priority in section_names:
                toc_entries.append(
                    f"- [{section_names[priority]}](#{section_names[priority].lower().replace(' ', '-').replace(',', '')})"
                )
            current_priority = priority

    llms_content.extend(toc_entries)
    llms_content.append("")
    llms_content.append("---")
    llms_content.append("")

    # Add file contents
    current_priority = None
    for file_path in sorted_files:
        try:
            priority = get_file_priority(file_path)

            # Add section header when priority changes
            if priority != current_priority:
                if priority in section_names:
                    llms_content.append(f"## {section_names[priority]}")
                    llms_content.append("")
                current_priority = priority

            # Read file content
            full_path = os.path.join(root_dir, file_path)
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if not content.strip():
                continue

            # Extract title and add file header
            title = extract_title_from_content(content, file_path)
            llms_content.append(f"### {title}")
            llms_content.append(f"**File:** `{file_path}`")
            llms_content.append("")

            # Add cleaned content
            cleaned_content = clean_content(content)
            llms_content.append(cleaned_content)
            llms_content.append("")
            llms_content.append("---")
            llms_content.append("")

        except Exception as e:
            print(f"Warning: Could not process {file_path}: {e}")
            continue

    # Footer
    llms_content.append("## End of Documentation")
    llms_content.append("")
    llms_content.append(
        "This concludes the comprehensive documentation for the Microsoft Agent Framework."
    )
    llms_content.append("For the latest updates, please visit the GitHub repository.")
    llms_content.append("")

    return "\n".join(llms_content)


def main():
    """Main function to generate llms.txt file."""
    root_dir = os.getcwd()

    print("Generating llms.txt file...")
    print(f"Repository root: {root_dir}")

    # Generate content
    content = generate_llms_txt(root_dir)

    # Write to file
    output_path = os.path.join(root_dir, "llms.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Generated llms.txt with {len(content.splitlines())} lines")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
