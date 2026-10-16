# Installed template library example

This rule-set package instantiates a template from a definitions package it
does not carry.

- `definitions.pkl` is the terminology the package carries: a wall, its
  `IsExternal` property, and the property set qualifying it.
- `ruleset.pkl` declares both `axioval:example.installed-library.terms` and
  `axioval:example.template-library` in `definitionPackages`, and binds the
  library's `boolean-property-equals` template.
- `axioval.json` names only the carried module in `definitionEntrypoints`.

A host resolves `axioval:example.template-library` from the definitions
packages it has installed. Supply `examples/template-library`, as a package
directory or as its `.mcs` archive, to validate, pack, and verify:

```bash
python3 scripts/validate.py --definitions examples/template-library
python3 scripts/mcs.py pack examples/template-library /tmp/library.mcs
python3 scripts/mcs.py pack examples/installed-library /tmp/rules.mcs \
  --definitions /tmp/library.mcs
python3 scripts/mcs.py verify /tmp/rules.mcs --definitions /tmp/library.mcs
```

Without the library, binding fails closed and names the unresolved ID. The
archive never carries the library.

The example is deliberately non-production.
