# Shared expression conformance fixtures

Each `*.json` file is a byte-for-byte copy of the engine's golden expression
fixture of the same name, one per expression node kind and one per literal
scalar kind, from `crates/contracts/ir/tests/fixtures/expression` of
[axioval/engine](https://github.com/axioval/engine) at commit
`58731ecaab9ef47baf32b26c4ae0b3218f46dbe4`. Do not edit them here: update
them from the engine and record the new commit.

Each `*.pkl` module authors the fixture of the same name with the MCS schema;
`Fixture.pkl` renders its `expression` alone. `tests/test_expressions.py`
proves that:

- the fixtures cover every expression kind the binder knows and every scalar
  literal kind;
- evaluating each module yields exactly the bytes of its fixture;
- every fixture binds as a rule's `expression` parameter in a package whose
  definitions declare the `ex:` concepts the fixtures name, packs into `.mcs`
  deterministically, verifies, and comes back byte for byte in the
  transport's canonical form (sorted keys, compact separators), the form
  `.mcs` stores normalized JSON in.

To check that the copies have not drifted, point `AXIOVAL_ENGINE_FIXTURES` at
the engine's fixture directory and run the tests:

```bash
AXIOVAL_ENGINE_FIXTURES=../engine/crates/contracts/ir/tests/fixtures/expression \
  python3 -m unittest tests.test_expressions -v
```
