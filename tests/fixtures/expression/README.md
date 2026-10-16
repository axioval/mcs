# Shared expression conformance fixtures

Each `*.json` file is a byte-for-byte copy of the engine's golden expression
fixture of the same name, one per expression node kind and one per literal
scalar kind, from `crates/contracts/ir/tests/fixtures/expression` of
[axioval/engine](https://github.com/axioval/engine) at commit
`0e1a0f6158372daa361307c10c71a7127e42ca23`. Do not edit them here: update
them from the engine and record the new commit.

Each `*.pkl` module authors the fixture of the same name with the MCS schema;
`Fixture.pkl` renders its `expression` alone. `tests/test_expressions.py`
proves that:

- the fixtures cover every expression kind the binder knows and every scalar
  literal kind;
- evaluating each module yields exactly the bytes of its fixture;
- every fixture binds as the operand of an `isDefined` rule `requirement` of
  `axioval:capability.expression` in a package whose definitions declare the
  capability's signature and the `ex:` concepts the fixtures name, each
  property of the value kind its fixtures use it as, packs into `.mcs`
  deterministically, verifies, and comes back byte for byte in the
  transport's canonical form (sorted keys, compact separators), the form
  `.mcs` stores normalized JSON in.

To check that the copies have not drifted, point `AXIOVAL_ENGINE_FIXTURES` at
the engine's fixture directory and run the tests:

```bash
AXIOVAL_ENGINE_FIXTURES=../engine/crates/contracts/ir/tests/fixtures/expression \
  python3 -m unittest tests.test_expressions -v
```
