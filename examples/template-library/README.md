# Template library example

This package is a definitions package: a library of rule templates published
without a rule set of its own.

- `definitions.pkl` declares two rule templates with bilingual names and
  parameters.
- `axioval.json` has `kind: "definitions"`, names the definition modules in
  `definitionEntrypoints`, and has no `entrypoint`.

A rule set instantiates these templates by naming
`axioval:example.template-library` in its `definitionPackages`. A host resolves
that ID from the definitions packages it has installed.

Evaluate the normalized representation:

```bash
pkl eval -f json definitions.pkl
```

The example is deliberately non-production.
