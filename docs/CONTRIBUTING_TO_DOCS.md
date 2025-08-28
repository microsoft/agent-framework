# Contributing to DOCS

To allow moving the docs to mslearn later, we are using language pivots as supported with mslearn markdown files.
This means that to make the docs easier to understand for users, we have a [PowerShell script](./generate-language-specific-docs.ps1) that generates language specific versions of the docs in separate folders.
The script strips out any pivots that are for a different language to the target.

Therefore, write your docs in the [docs-templates](./docs-templates/) folder and then
generate the language-specific versions by just running the PowerShell script.

```powershell
.\generate-language-specific-docs.ps1
```

## Using pivots

To have language-specific content, use the `::: zone pivot` syntax in your markdown file.
Note that when using a pivot you always have to have a section for both languages (csharp and python).

```text
::: zone pivot="programming-language-csharp"

C# specific content.

::: zone-end
::: zone pivot="programming-language-python"

Python specific content.

::: zone-end
```
