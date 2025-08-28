# Contributing to DOCS

To allow moving the docs to mslearn later, we are using language pivots as supported with mslearn markdown files.
This means that to make the docs easier to understand for users, we have a [PowerShell script](./generate-language-specific-docs.ps1) that generates language specific versions of the docs in separate folders.

Therefore, write your docs in the [docs-templates](./docs-templates/) folder and then
generate the language-specific versions by just running the powershell script.