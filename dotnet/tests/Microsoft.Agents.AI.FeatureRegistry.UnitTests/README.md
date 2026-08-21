# .NET feature registry validation

This project parses the .NET v1 table in
`docs/specs/feature-usage-bit-registry.md` and validates package-local
`FeatureIndex` declarations.

The tests validate allocation, ownership, naming, range, uniqueness, external
exceptions, complete in-repository coverage, and production activation
references for every local feature index.
