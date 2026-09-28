# Changelog

All notable changes to Axioval MCS are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
package/schema compatibility follows [Semantic Versioning](https://semver.org/)
once a release is tagged. The current `0.1.0` contract is pre-stable.

## [Unreleased]

### Added

- Property selectors and property references name the reserved attribute sets
  `axioval:attributes`, `axioval:type-attributes`, `axioval:presentation`,
  `axioval:material`, and `axioval:body`, as category levels already do. The
  set binds to itself; the property in it is still a property concept bound
  through the catalogs. A property-set pattern never searches these sets.
- A `related` selector's `path` may name relationships the checking
  application derives from geometry, as a category path may:
  `axioval:derived.<name>` with optional `;key=value` tolerances, a direction,
  and `+`, such as `axioval:derived.adjacent-space;reach=1`.
- Values measured from geometry, mirroring the engine: the reserved set
  `axioval:measured` names `extent_x`, `extent_y`, `extent_z`, `bottom`, `top`,
  `area`, `volume`, `x`, `y`, `z`, and `level_height`, and, with `;key=value`
  parameters, `bottom_above_level;path=<steps>` and
  `boundary_area;kind=<kind>[;plane=<metres>]`, matched ignoring ASCII case, in
  selectors, property references, and category levels. They bind to no
  concept; the binder rejects any other name in that set, a missing `path` or
  `kind`, malformed path steps, a `plane` below zero or not a number, repeated
  and unknown parameters, and compares a measured value with a `quantity`.
- Classifications a ruleset derives, mirroring the engine: `classifications`
  (`RuleSets.ClassificationDefinition`, by ID) with a `name`, an optional
  `description`, a `mode` `firstMatch` (default, omitted from normalized JSON)
  or `allMatch`, and ordered `rows` (`RuleSets.ClassificationRow`) of a
  `selector` and a `class`; normalized JSON omits an empty map. Selectors,
  property references, and category levels name a classification as a
  property in the reserved set `axioval:classification`, which binds to no
  concept. The binder checks exact keys, non-blank IDs equal to their keys,
  non-empty rows with non-blank classes, row selectors bound against the
  concepts and free of `ruleOutcome` selectors, no cycle among
  classifications, and that every reference names a declared classification.
- Rule gates and rule-outcome selectors, mirroring the engine: a rule instance
  or rule folder may declare a `gate` (`RuleSets.RuleGate`) on another rule of
  the same ruleset, a `rule` ID and a `condition` `allIfPassed`, `allIfFailed`,
  `passedObjects`, or `failedObjects`; a folder's gate applies to every rule in
  it and must name a rule outside it. A `ruleOutcome` selector
  (`Selectors.RuleOutcomeSelector`) selects the objects another rule `passed`
  or `failed`. Normalized JSON omits an unset gate. The binder checks exact
  keys, that every referenced rule is a rule instance of the same ruleset,
  also a disabled one, and rejects a rule depending on its own outcome and
  rules depending on one another's outcomes in a cycle.
- The presence operators `isEmpty` (present but null, blank text, or a list of
  nothing else) and `isNotEmpty` (present with a value), which, like `exists`,
  take no value, no quantifier, and no text option on property,
  property-pattern, and source selectors.
- A classification selector may name codes by `codePattern`, an XML Schema
  pattern over the whole code checked like a property-name pattern, or with
  neither `code` nor `codePattern` select any classification in its `system`.
  `code` becomes optional, normalized JSON omits an unset `code` or
  `codePattern`, and Pkl and the binder reject both together and
  `includeDescendants: true` with neither.
- A `source` selector (`Selectors.SourceSelector`) that compares a source's
  `fileName`, `application`, `schema`, or `project` as a property selector
  compares a text value, with `caseSensitive`, `trim`, and `quantifier`
  omitted at their defaults. It binds no concept, and the binder rejects any
  other field or key.
- Rule-instance refinements, mirroring the engine's rule instance, each
  optional and omitted from normalized JSON when empty: `severityBands`
  (`RuleSets.SeverityBand`, a finite `below` threshold above zero of the
  relative deviation and a `severity`, thresholds strictly ascending),
  `severityOverrides` (`RuleSets.SeverityOverride`, a `selector` bound against
  the concept catalogs and a `severity`), and `categories`
  (`RuleSets.CategoryLevel`, a property concept, an optional property-set
  concept or reserved set such as `axioval:attributes`, and an optional
  related-selector `path` that may also name derived relationships). The binder
  checks exact keys and rejects empty lists.
- Table columns of kind `date` and `dateTime`, whose cells are
  `Values.DateValue` and `Values.DateTimeValue` literals checked like any other
  date or date-time, so a table row can bound a value by date.
- A `propertyPattern` selector (`Selectors.PropertyPatternSelector`) that
  selects an object by the properties whose names match XML Schema patterns:
  `propertyPattern` and an optional `propertySetPattern`, matched against the
  source's own names and never bound through the concept catalogs, and
  `matched` (`any` or `all`) over the matching properties, no match being no
  match. `operator`, `value`, `caseSensitive`, `trim`, `quantifier`, and
  `precision` compare each matched value as on a property selector, and
  normalized JSON omits their defaults. The binder checks exact keys,
  `matched`, and that both patterns are non-empty and valid, rejecting
  character-class subtraction, `\i`/`\c` name escapes, and `\p{Is…}` block
  escapes.
- A `discipline` selector, `{"kind": "discipline", "value": "<token>"}`
  (`Selectors.DisciplineSelector`), that selects the objects of the sources
  declaring that discipline; an object whose source declares none is not
  evaluated, never a non-match. The token is 1 to 64 lowercase ASCII letters,
  digits, `-`, or `_`, starting with a letter or digit, and no vocabulary is
  fixed. Pkl and the binder reject any other token and any key besides `kind`
  and `value`; the selector nests like any other selector.
- `date` and `dateTime` values (`Values.DateValue`, `Values.DateTimeValue`) as
  parameter kinds and property `valueKind`s. The binder checks literals by the
  engine's rules: a real `YYYY-MM-DD` day in the years 0000 to 9999, and a
  date-time with a time from 00:00:00 to 23:59:59, up to nine fraction digits,
  and a required offset `Z` or `±hh:mm` of at most 14 hours, refusing `-00:00`.
  Property selectors order dates and date-times and take an optional
  `precision` `day`, only with a `date` or `dateTime` value, that compares a
  date-time with a date by the day it states; normalized JSON omits it when
  unset.
- A `related` selector that selects an object by the objects a relationship
  `path` reaches from it: steps `Relationship` or `Relationship:direction`
  (`forward`, `backward`, or `either`), a nested `selector`, and a `quantifier`
  `any` (default, omitted from normalized JSON), `all`, or `none`. The binder
  checks exact keys, a non-empty path of well-formed steps, the quantifier, and
  binds the nested selector against the concept catalogs.
- Table-valued rule parameters: a `table` parameter declares named `columns`,
  each with a kind (`string`, `textPattern`, `number`, `quantity` with a
  `unitDimension`, `integer`, `boolean`, `selector`, or `reference`) and a
  `required` flag, and its `TableValue` is a list of rows mapping column IDs to
  cells of those kinds. The binder rejects unknown columns, cells of another
  kind, missing required cells, malformed text patterns, columns on other
  parameter kinds, and `allowedValues` on tables, for bound rows and defaults
  alike. Normalized JSON omits `columns` elsewhere, so existing packages render
  unchanged.
- An optional property selector `quantifier`, `any` or `all`, that compares a
  list-valued (`stringList` or `referenceList`) property element by element;
  normalized JSON omits it when unset. The binder rejects other values and a
  quantifier on `exists`, checks a quantified `value` against the element kind,
  and requires a quantifier on every comparison of a list-valued property.
- Property selector operators `like` (whole-value wildcards), `contains`,
  `oneOf`, and `noneOf`, plus `caseSensitive` and `trim` text options that
  normalized JSON omits at their defaults. The binder requires a `string` for
  `matches`, `like`, and `contains`, a `stringList` whose elements fit the
  property's value kind for `oneOf` and `noneOf`, ordered value kinds for
  ordering operators, and text comparisons for non-default text options.
- Authoring adapters for version-bound `openbim.ifc` references and closed
  `openbim.geometry` capability IDs, plus an IFC4X3 directional-clearance example.
- MCS source-closure support for checksum-locked Pkl package imports, with
  declared-alias binding, required lock coverage, fresh-cache checksum
  reauthentication during packing, and explicit package-path traversal rejection.
- Deterministic, fail-closed `.mcs` transport tooling with exact source topology,
  normalized declarative payloads, complete checksummed inventory, bounded ZIP
  parsing, sandboxed source re-evaluation, and bilingual format documentation.
- Structured package source catalogs, citations, ordered bibliographic locators,
  requirement citations, and explicit bound-parameter citation targets.
- Targetable applicability groups and rule requirements that bind localized
  expected-state statements to named element populations.
- Package-contained explanatory images with localized alternative text and
  captions, safe relative paths, media declarations, content validation, and a
  10 MB per-image safety limit.
- MkDocs Material documentation site and GitHub Pages deployment.
- Reusable `ObjectTypeDefinition`, `PropertyDefinition`, and independent
  `PropertySetDefinition` vocabulary components.
- Canonical `ObjectTypeReferenceValue` and `PropertyReferenceValue` variants.
- Boxed `SelectorValue` parameters for capabilities that require an independent
  secondary object scope, with recursive fail-closed concept binding.
- Optional exact property-set qualification without property ownership.
- `referencedValueKind` constraints for typed property-reference parameters.
- Full DIN 276 KG 331 instructional fixture covering object type, strict
  `LoadBearing`, and container-agnostic `IsExternal` requirements.
- Negative tests for unknown concepts and property-kind mismatches.
- Contributor guide, roadmap, AGPL license, and GitHub Sponsors configuration.
- Accessible local SVG diagrams with separate wide and mobile compositions.
- A build-time prose guard that rejects en and em dashes in repository Markdown.
- Complete German suffix translations, localized navigation, and translated SVG diagrams.
- Browser-language routing with a persistent manual German and English selector.
- Source-level regression tests for locale coverage, disclosures, diagrams, task lists,
  and bounded text-only navigation.

### Changed

- `PackageMetadata.name` and `description` now use `LocalizedText`.
- Entity-type selectors now reference reusable object-type concepts instead of
  repeating raw external type-system/name pairs.
- The minimal property example uses one canonical property reference rather than
  treating `propertySet` and `property` as peer string parameters.
- Definition-package normalized output now includes object, property, and
  property-set catalogs.
- IFC entity bindings now use the release's semantic HTTPS type-system identity
  from `openbim.ifc@0.2.0`; project property/set examples use their own
  namespace until package-owned PSD/QTO occurrences ship.
- The public site now opens with a plain-language, three-page picture tour and
  keeps tool-builder reference material in a separate path.
- Tutorial source and validation commands are collapsed by default, while
  remaining statically highlighted and available on demand.
- All reader and reference source panels now stay closed until requested.
- Documentation caps the main column at 800 pixels and aligns prose, headings,
  diagrams, cards, and tables to one shared edge.
- Publication task lists render as styled, accessible checkboxes.
- Trusted local diagrams inherit the active light or dark site palette after
  safe site-level inlining, with static images as the no-script fallback.

### Fixed

- Apple Pkl code fences now use a dedicated server-side lexer, including
  arbitrary-length custom string delimiters, and fail the docs build if they
  regress to unhighlighted plain text.
- Dark-mode diagrams theme an explicit SVG canvas, including the gradient-backed
  Start artwork.
- Documentation typography and spacing remain stable at wide desktop breakpoints.
- Definition-default validation no longer shadows the active ruleset document
  while binding.

### Security

- Sandboxed Pkl evaluation permits checksum-locked package/project-package modules
  and their required host-scoped HTTPS metadata and release assets while retaining
  arbitrary HTTPS, file, and environment resource denial plus the repository root
  boundary. The gate re-resolves a copied project with an empty cache and requires
  its generated dependency lock to match the committed bytes.
- Citation binding rejects unknown source and parameter references, duplicate IDs
  and locators, malformed publication dates, and non-HTTPS or credential-bearing
  source URLs.
- Normalization rejects unknown object/property/property-set IDs, mismatched
  referenced property kinds, and unresolved strict container qualifiers.

## [0.1.0] - 2026-08-31

### Added

- Initial Pkl authoring modules for types, values, selectors, definitions, and
  rule sets.
- Static `axioval.json` registry manifest contract.
- Repository-confined Pkl evaluation and deterministic normalized snapshots.
- Fail-closed cross-document package, definition, selector, and parameter binder.
- Minimal non-production package and CI validation workflow.

[Unreleased]: https://github.com/axioval/mcs/compare/49a2d765fe9a6a5b2f9cbf650500c30b9d6068d3...HEAD
[0.1.0]: https://github.com/axioval/mcs/commit/49a2d765fe9a6a5b2f9cbf650500c30b9d6068d3
