---
name: regex-tester
description: Validate, test, and debug regular expressions by executing them against sample inputs. Use when asked to build, verify, or explain a regex pattern.
---

## Usage

When the user asks you to create, validate, or debug a regular expression:

1. **Understand the requirement** — clarify what the pattern should match and what it should reject.
2. **Consult the cheatsheet** — review `references/regex-cheatsheet.md` for syntax reminders if needed.
3. **Write and execute test code** — use the `execute_code` tool to run Python code that:
   - Compiles the regex with `re.compile()`
   - Tests it against a set of positive examples (should match) and negative examples (should not match)
   - Extracts and displays any capturing groups
   - Reports pass/fail for each test case
4. **Iterate** — if any test fails, refine the pattern and re-run until all cases pass.
5. **Present the result** — give the user the final pattern, explain what each part does, and show the test results.

## Example Test Script

```python
import re

pattern = re.compile(r'^[\w.+-]+@[\w-]+\.[\w.-]+$')

positives = ["user@example.com", "first.last+tag@sub.domain.org"]
negatives = ["@missing.com", "no-at-sign", "spaces in@address.com"]

for s in positives:
    assert pattern.match(s), f"FAIL: expected match for '{s}'"
for s in negatives:
    assert not pattern.match(s), f"FAIL: expected no match for '{s}'"

print("All tests passed!")
```
