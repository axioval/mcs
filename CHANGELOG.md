# Changelog

All notable changes to Axioval MCS are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
package/schema compatibility follows [Semantic Versioning](https://semver.org/)
once a release is tagged. The current `0.1.0` contract is pre-stable.

## [Unreleased]

### Added

- `MeetsSelector` (`kind: "meets"`), which selects the objects meeting a trusted,
  selectable capability's requirement on their own. The binder validates its
  qualified capability ID, parameter identifiers, value variants, and referenced
  concepts.
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
