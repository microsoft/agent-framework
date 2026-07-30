# Regex Quick Reference (Python `re` module)

## Character Classes

| Pattern | Matches |
|---------|---------|
| `.`     | Any character except newline |
| `\d`    | Digit `[0-9]` |
| `\D`    | Non-digit |
| `\w`    | Word character `[a-zA-Z0-9_]` |
| `\W`    | Non-word character |
| `\s`    | Whitespace `[ \t\n\r\f\v]` |
| `\S`    | Non-whitespace |
| `[abc]` | Any of a, b, or c |
| `[^abc]`| Any character except a, b, c |
| `[a-z]` | Range: a through z |

## Quantifiers

| Pattern | Meaning |
|---------|---------|
| `*`     | 0 or more (greedy) |
| `+`     | 1 or more (greedy) |
| `?`     | 0 or 1 (greedy) |
| `{n}`   | Exactly n |
| `{n,}`  | n or more |
| `{n,m}` | Between n and m |
| `*?`, `+?`, `??` | Non-greedy versions |

## Anchors

| Pattern | Meaning |
|---------|---------|
| `^`     | Start of string (or line with `re.MULTILINE`) |
| `$`     | End of string (or line with `re.MULTILINE`) |
| `\b`    | Word boundary |
| `\B`    | Non-word boundary |

## Groups and Backreferences

| Pattern | Meaning |
|---------|---------|
| `(...)` | Capturing group |
| `(?:...)`| Non-capturing group |
| `(?P<name>...)` | Named group |
| `\1`    | Backreference to group 1 |
| `(?=...)` | Positive lookahead |
| `(?!...)` | Negative lookahead |
| `(?<=...)` | Positive lookbehind |
| `(?<!...)` | Negative lookbehind |

## Flags

| Flag | Effect |
|------|--------|
| `re.IGNORECASE` / `re.I` | Case-insensitive matching |
| `re.MULTILINE` / `re.M`  | `^`/`$` match line boundaries |
| `re.DOTALL` / `re.S`     | `.` matches newline |
| `re.VERBOSE` / `re.X`    | Allow comments and whitespace |

## Common Patterns

| Use Case | Pattern |
|----------|---------|
| Email (simple) | `^[\w.+-]+@[\w-]+\.[\w.-]+$` |
| IPv4 address | `^\d{1,3}(\.\d{1,3}){3}$` |
| ISO date | `^\d{4}-\d{2}-\d{2}$` |
| URL (http/https) | `^https?://[^\s/$.?#].[^\s]*$` |
| Phone (US) | `^(\+1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$` |

## Python API

```python
import re

# Test if a string matches
re.match(r'pattern', "string")       # match at start
re.search(r'pattern', "string")      # match anywhere
re.fullmatch(r'pattern', "string")   # match entire string

# Find all matches
re.findall(r'\d+', "abc 123 def 456")  # ['123', '456']

# Named groups
m = re.match(r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})', "2025-01-15")
m.group('year')   # '2025'

# Replace
re.sub(r'\d+', 'X', "abc 123 def")   # 'abc X def'

# Split
re.split(r',+', "a,b,,c")            # ['a', 'b', 'c']

# Compile for reuse
pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
pattern.match("2025-01-15")           # Match object
```
