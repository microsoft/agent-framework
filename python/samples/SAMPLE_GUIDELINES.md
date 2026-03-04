# Python Sample Guidelines

These guidelines apply to all Python samples under `python/samples/`. They are
intended to mirror the structure and design principles used by the .NET
samples, while following Python-specific conventions.

## File structure

Every sample file should follow this order (see also
`python/.github/skills/python-samples/SKILL.md`):

1. PEP 723 inline script metadata (if external dependencies are needed)
2. Copyright header:
   `# Copyright (c) Microsoft. All rights reserved.`
3. Required imports
4. Module-level docstring describing what the sample demonstrates
5. Helper functions
6. Main function(s) demonstrating the core scenario
7. Entry point:
   `if __name__ == "__main__": asyncio.run(main())`

External, sample-only dependencies should be declared via PEP 723 metadata and
**not** added to the root `pyproject.toml` dev group.

## Documentation

Samples should be slightly over-documented so that new users can follow along:

- Each group of samples (folder) should have a `README.md` that explains the
  purpose of the samples and how to run them.
- Inside each sample file, add a short docstring under the imports explaining
  the scenario and key components.
- For multi-step flows, use numbered comments like:

  ```python
  # 1. Create the client instance.
  ...
  # 2. Create the agent with the client.
  ...
  ```

- For non-trivial samples, include a short "Sample output" block at the bottom
  of the file so users know what to expect when they run it.

### **Consistent Structure**

The canonical folder layout for Python samples is documented in
`python/samples/AGENTS.md` and summarized in `python/samples/README.md`. In
short:

- Top-level folders are **numbered sections** (`01-get-started/`,
  `02-agents/`, `03-workflows/`, `04-hosting/`, `05-end-to-end/`), plus
  migration folders such as `autogen-migration/` and `semantic-kernel-migration/`.
- `03-workflows/` keeps the upstream workflow sample structure intact (do not
  rename or restructure those samples).
- Extension- or provider-specific samples (for example under a package like
  `python/packages/redis/`) should mirror the same numbering and be linked from
  the top-level `python/samples/README.md`.

### **Author checklist**

When adding or updating a sample, try to ensure:

1. The file lives in the correct folder for its **concept** and **complexity**
   (follow the structure in `AGENTS.md` and the numbered sections in
   `python/samples/README.md`).
2. The sample follows the file structure listed at the top of this document
   (PEP 723 metadata when needed, copyright, imports,
   `load_dotenv()`, docstring, helpers, `main()`, entry point).
3. There is a short README for each sample set (folder) explaining purpose and
   how to run the samples.
4. If the sample is non-trivial or demonstrates a subtle behavior, there is
   either an automated test or at least a note in the README about expected
   output and edge cases.

