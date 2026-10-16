# Safe package acceptance

Before a shared bundle reaches a checking tool, Axioval opens it through a fixed
series of safety gates. Each gate answers one plain question: are the files where
they should be, can they be opened safely, do all references make sense, and does
the result match the reviewed snapshot?

Every package follows the same path. A package owned by Axioval receives no extra
permissions or trust.

<div class="diagram-frame" markdown>

![A package is inspected, opened safely, checked completely, and handed to a compatible tool](assets/images/trust-path.svg)

</div>

## Required files

??? example "Show the required files"
    ```text
    axioval.json      # static discovery manifest
    PklProject        # pinned Pkl project boundary
    <entry>.pkl       # ruleset module named by axioval.json (ruleset only)
    <definition>.pkl  # definition modules named by axioval.json
    ```

The manifest **must** validate against
`schema/registry-manifest.schema.json`. Entrypoints are repository-relative Pkl
paths. Absolute paths, `..` traversal, unknown fields, missing modules, and
non-Pkl entrypoints are forbidden.

## Package kinds

The manifest's `kind` says what a package publishes:

- `ruleset` names its rule set in `entrypoint` and the definition modules it
  carries in `definitionEntrypoints`. Both are required.
- `definitions` publishes a library of definitions, such as rule templates,
  without a rule set. It names its modules in `definitionEntrypoints` and
  **must not** have an `entrypoint`. Its documents must bind together as a
  rule set would load them: package, template and concept IDs are unique
  across them. The manifest's `id` and `version` must be the package identity
  of exactly one of its definition documents.

A rule set names every definition package it binds by ID in
`definitionPackages`, and binds against exactly the declared packages:

- every definition document the rule-set package carries **must** be declared;
  a carried package the rule set does not declare is refused;
- each declared ID the package does not carry resolves from the definitions
  packages the host has installed, or the caller supplies, by the package ID
  of their definition documents. An ID that resolves to no document, or to
  more than one, fails closed and names the ID;
- a carried package wins over a supplied one of the same ID, and a supplied
  package the rule set does not declare is ignored, not bound;
- resolved documents bind together with the carried ones under the same
  uniqueness and kind checks, each with its own package's assets.

The rule set never fetches definitions on its own, and its archive never
carries the packages it resolves. `validate.py`, `mcs.py pack` and
`mcs.py verify` take supplied definitions packages with `--definitions PATH`,
repeatable: a `.mcs` archive, verified first and refused unless its kind is
`definitions`, or a package directory with a definitions-kind `axioval.json`.
`examples/installed-library` declares `axioval:example.template-library`
without carrying it and binds only when `examples/template-library` is
supplied.

!!! warning
    A host **should** run `verify` on an archive from an untrusted registry
    before installing it. `inspect` checks structure, hashes and identity
    only; it does not re-evaluate the source.

## Ordered trust boundary

The order is part of the security contract:

1. parse `axioval.json` as untrusted static data;
2. validate every field against the manifest JSON Schema;
3. resolve **all** ruleset and definition paths inside the repository root;
4. re-resolve a copied Pkl project with an empty cache and require its generated
   dependency lock to match the committed bytes;
5. evaluate Pkl with repository-local, standard-library, and checksum-locked
   package modules; HTTPS resources are limited to the OpenBIM package metadata,
   stable release, and signed release-asset hosts, while arbitrary HTTPS, file,
   and environment resource reads remain forbidden;
6. validate every candidate definition document;
7. bind declared packages, source catalogs, citations, object types, properties,
   property-set qualifiers, templates, applicability groups, requirements,
   selectors, typed parameter values, and explanatory image assets; a
   definitions package binds its definition documents together instead;
8. reject duplicate, missing, unknown, conflicting, malformed, or unsupported
   declarations; and
9. compare semantically validated output with checked normalized snapshots.

!!! danger
    Evaluator output before step 6 is **candidate JSON**, not normalized
    interchange. A successful Pkl process is not proof of a valid package.

## Authoring and runtime separation

Pkl source may use imports, local values, and authoring helpers. Evaluation must
lower all of that to declarative data. Applications execute only capabilities
they already implement; they never execute package-supplied model-checking code.

## Property-resolution contract

A property reference always names a canonical `PropertyDefinition`.

- With no `propertySet`, adapters resolve it across supported containers.
- With `propertySet`, adapters require that exact canonical container relation.
- Multiple incompatible resolutions are conflicts, not arbitrary winners.
- `referencedValueKind` must agree with the referenced property definition.

Property-set qualifiers do not own properties and are not execution folders.

## Selector-valued parameters

A capability that needs a second object scope declares a parameter with
`kind = "selector"`. The rule binds a complete selector using
`SelectorValues.SelectorValue`; it must not reduce the scope to a raw type name
or an executable callback.

??? example "Show a selector-valued parameter"
    ```pkl
    import "Selectors.pkl"
    import "SelectorValues.pkl"

    parameters {
      ["compared"] = new SelectorValues.SelectorValue {
        value = new Selectors.AllOfSelector {
          operands {
            new Selectors.EntityTypeSelector {
              objectType = "axioval:example.ifc.wall"
            }
          }
        }
      }
    }
    ```

The normalized value has `type: "selector"` and a nested selector object. The
binder recursively validates that object and resolves every object-type and
property concept through the loaded definition packages. Unknown concepts,
malformed operands, and unsupported value combinations fail closed.

## Expression-valued parameters

A capability that computes a value per object declares a parameter with
`kind = "expression"`. The rule binds a declarative expression tree using
`Expressions.ExpressionValue`; normalized, it has `type: "expression"` and the
tree as `value`. The tree is data, never code: the checking application
evaluates it with a capability it already implements, and an application
without one fails closed.

The binder checks the tree's structure and limits, binds every property to a
declared concept or a derived-set name, every embedded selector as any
selector, every `derived` node to a value the ruleset declares, and every
`parameter` and `lookup` node to a parameter the rule binds or defaults. An
expression value for a parameter of any other kind is rejected. See
[Compute with expressions](expressions.md).

## Citation contract

Every ruleset and definition document declares its own source catalog. Citations
must resolve inside that catalog. Definition components, rules, and requirements
may cite a source directly; `parameterCitations` must name non-empty, unique
parameter IDs that the same rule actually binds. Citation IDs are unique within
their containing rule or definition component, and duplicate locators are
rejected.

Source URLs are optional. When present, they must be absolute HTTPS URLs without
embedded credentials. Publication dates use valid ISO `YYYY`, `YYYY-MM`, or
`YYYY-MM-DD` forms. Localized source titles and notes use the same fail-closed
localization contract as rule text.

A citation records provenance only. It must never alter selectors, requirements,
evidence, pass or fail outcomes, legal status, or conformance claims. Store
bibliographic metadata and pinpoint locators rather than copyrighted normative
text.

## Package image assets

Explanatory images are data, not executable extensions. Their paths must remain
inside the package. Callers must provide the package root whenever a ruleset
references images; the binder rejects image-bearing rulesets when that root is
missing. It resolves every referenced file, checks the size, extension, declared
media type, and file signature, and parses SVG as inert XML. Active elements,
event handlers, external links, document types, processing instructions, style
content, and foreign SVG content fail closed. Consumers should still apply their
own image decoding and rendering sandbox.

## Package table files

A `tableFile` value names a CSV file or an `.xlsx` workbook in the package whose
rows fill a table, and pins its bytes with a SHA-256. Table files are data, not
executable extensions: the binder needs the package root, as for images, keeps
every path inside the package, rejects files over 10,000,000 bytes or with
another digest, and takes each cell as written. Workbook formulas, error cells,
document types, and processing instructions fail closed.

## Source and compiled forms

Pkl source is authoritative for editing. A registry may cache validated
normalized JSON, but generated output alone is not proof that source is safe or
valid. Cache keys should include the immutable source revision, schema version,
Pkl version, and validator version.

## Licensing and provenance

Package authors choose their own license and repository host. Registry listing
does not transfer ownership or imply endorsement. Axioval-owned packages are
ordinary packages validated through the same pipeline.
