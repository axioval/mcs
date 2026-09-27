# Schema surface

This is the precise reference for people connecting software to Axioval. If you
only want to understand or prepare a check, start with the
[four building blocks](../guide/building-blocks.md) instead.

The Pkl modules define what authors may write. The Python binder is the final
safety gate before checked information becomes normalized JSON. All examples are
folded by default so you can scan the concepts first.

## Modules

| Module | Owns |
| --- | --- |
| `Types.pkl` | identifiers, semantic versions, localized text, package metadata |
| `Citations.pkl` | bibliographic sources, locators, citations, parameter targets |
| `Values.pkl` | tagged scalar/list values plus object/property references |
| `Selectors.pkl` | object type, property, classification, boolean-composition selectors |
| `Definitions.pkl` | vocabularies and reusable capability templates |
| `RuleSets.pkl` | concrete rule instances and cosmetic folders |

## Package metadata and citations

`PackageMetadata.name` and `description` use `LocalizedText`; package authors no
longer combine languages in one string. Each definition or ruleset document owns
a `sources` catalog. A source records a kind, formal designation, localized
title, and optional publisher, edition, ISO publication date, and HTTPS URL.

A `Citation` points to one source and may add ordered locators such as part,
clause, paragraph, table, figure, or page. Definition components, rules, and
requirements can carry citations. `parameterCitations` applies one citation to
explicit parameters that are actually bound by that rule. Unknown source IDs,
unsafe URLs, invalid dates, duplicate citation IDs or locators, and unknown
parameter targets fail closed.

Citations are provenance metadata only. They do not change applicability,
evidence, evaluation, verdicts, legal force, or compliance claims.

## Definition package

A normalized definition document has these top-level fields:

??? example "Show the normalized document shape"
    ```json
    {
      "schemaVersion": "0.1.0",
      "package": {},
      "sources": {},
      "objectTypes": {},
      "properties": {},
      "propertySets": {},
      "definitions": {}
    }
    ```

At least one reusable component must be present. Map keys must equal component
IDs. Duplicate component IDs across loaded packages are rejected.

### `ObjectTypeDefinition`

Maps one stable Axioval object-type ID to external-schema names such as
`IfcWall`. Object-type references can specify whether subtypes are accepted.

### `PropertyDefinition`

Maps one stable property ID to external names and one `valueKind`. Quantity
properties also require a qualified `unitDimension`. The property is independent
of any container.

### `PropertySetDefinition`

Maps one stable qualifier ID to external container names. It contains no member
list and establishes no ownership relation.

### `RuleDefinition`

Declares a capability and typed parameter map. `referencedValueKind` is valid
only on a `propertyReference` parameter and constrains the referenced property's
catalogued type.

### Table parameters

A `table` parameter carries rows of patterns and limits in one rule, such as a
minimum area per space type, instead of one rule per row. It declares its
`columns`, each with an `id`, a localized `name`, an optional `description`, a
`kind`, and whether it is `required` (the default):

| Column kind | Cell value |
| --- | --- |
| `string` | `string` |
| `textPattern` | `string`, read as a wildcard pattern matching the whole value: `*` any run of characters, `?` one character, `\` escapes the next character |
| `number` | `number` |
| `quantity` | `quantity`; the column requires a `unitDimension` |
| `integer` | `integer` |
| `boolean` | `boolean` |
| `selector` | `selector` |
| `reference` | `reference` |

A table value is a list of rows. Each row maps column IDs to cells of the
column's kind. The binder rejects a row with an unknown column, a cell of
another kind, a missing required cell, or a text pattern ending in an unpaired
backslash, whether the row is bound in a rule or is part of the `defaultValue`.
Concepts named in selector cells must resolve like any selector. Column IDs are
unique, `columns` is required on a table and invalid on every other kind, and a
table declares no `allowedValues`. An empty table is valid.

Normalized JSON omits `columns` on every other parameter, so existing packages
render unchanged. Which row applies (the first match, the most specific match,
or every match) is the capability's contract, not the package's.

??? example "Show a table parameter with a default"
    ```pkl
    ["limits"] {
      id = "limits"
      name { default = "Limits per space type" }
      kind = "table"
      columns {
        new { id = "space_type"; name { default = "Space type" }; kind = "textPattern" }
        new {
          id = "minimum_area"
          name { default = "Minimum area" }
          kind = "quantity"
          unitDimension = "area"
        }
      }
      defaultValue = new Values.TableValue {
        value {
          new {
            ["space_type"] = new Values.StringValue { value = "Office*" }
            ["minimum_area"] = new Values.QuantityValue { value = 10; unit = "m2" }
          }
        }
      }
    }
    ```

## Reference values

=== "Object type"

    ??? example "Show JSON"
        ```json
        {
          "type": "objectTypeReference",
          "objectType": "axioval:example.ifc.wall",
          "includeSubtypes": true
        }
        ```

=== "Property, loose"

    ??? example "Show JSON"
        ```json
        {
          "type": "propertyReference",
          "property": "axioval:example.ifc.is-external"
        }
        ```

=== "Property, strict"

    ??? example "Show JSON"
        ```json
        {
          "type": "propertyReference",
          "property": "axioval:example.ifc.load-bearing",
          "propertySet": "axioval:example.ifc.pset-wall-common"
        }
        ```

## Selectors

Selectors are declarative and recursively validated:

- `all`
- `entityType` using a canonical object-type ID
- `property` using a canonical property ID and optional set qualifier
- `classification`
- `allOf`, `anyOf`, and `not`

A comparison value on a property selector must match the referenced property's
catalogued `valueKind`. `exists` rejects a comparison value; every other
operator requires one.

| Operator | Value | Meaning |
| --- | --- | --- |
| `equals`, `notEquals` | the property's kind | equal or not equal |
| `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals` | `integer`, `number`, `quantity`, or `string` | ordered comparison |
| `matches` | `string` | regular expression matching the whole value |
| `like` | `string` | wildcard pattern matching the whole value: `*` any run of characters, `?` one character, `\` escapes the next character |
| `contains` | `string` | the value contains the text as a substring |
| `oneOf`, `noneOf` | `stringList` | the value is, or is not, one of the listed texts; each element must be a value of the property's kind |
| `exists` | none | the property has a value |

Two optional flags tune text comparisons, meaning any comparison of a `string`,
`enum`, or `reference` value and the operators `matches`, `like`, `contains`,
`oneOf`, and `noneOf`:

- `caseSensitive: false` compares without regard to case. The default is `true`.
- `trim: true` strips leading and trailing whitespace from the resolved property
  value before comparing. The declared `value` is never trimmed. The default is
  `false`.

Normalized JSON omits both flags when they keep their defaults, so existing
packages render unchanged. Setting either away from its default on `exists` or
on a comparison that is not text is rejected.

??? example "Show a case-insensitive wildcard selector"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.ifc.reference"
      operator = "like"
      value = new Values.StringValue { value = "EI*" }
      caseSensitive = false
      trim = true
    }
    ```

### List-valued properties

A property concept with `valueKind` `stringList` or `referenceList` is
list-valued: the application may resolve several values for it, such as every
presentation layer of an object. A list is never compared as a whole. A
comparison of a list-valued property states a `quantifier`, and its `value`
then fits the element kind, `string` or `reference`:

- `any` holds when at least one element satisfies the comparison;
- `all` holds when every element does, and never for an empty list.

A single value counts as a one-element list, so a quantifier is also accepted
on a scalar property. `exists` takes no quantifier, and any other `quantifier`
value is rejected. Normalized JSON omits an unset quantifier, so existing
packages render unchanged.

"Every layer is agreed" is `oneOf` with `quantifier = "all"`, "at least one
layer is agreed" the same with `"any"`, and "no layer is forbidden" `noneOf`
with `"all"`.

??? example "Show a quantified layer selector"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.ifc.layers"
      operator = "oneOf"
      value = new Values.StringListValue { value { "A-WALL"; "A-DOOR" } }
      quantifier = "all"
    }
    ```

## Rich applicability

A rule that involves several populations uses an `Applicability` object. Its
`groups` map gives every population a stable local ID, localized name, optional
description, and recursively validated selector. Requirements and trusted host
adapters can target these groups by ID.

For example, an opening-coordination rule can name separate groups for
penetrated elements, penetrating elements, and openings without pretending they
are one flat selection. Group-map keys must equal group IDs. Empty group maps,
unknown concepts, and malformed selectors are rejected.

Legacy rules may still provide one selector directly. Requirements need rich
applicability because a flat selector has no targetable group IDs.

## Requirements

A `Requirement` records a stable ID, localized statement, optional description,
and one or more `targetGroups`. Every referenced group must exist in the same
rule. Requirement IDs and group references must be unique.

Requirements explain the expected state. They do not execute package code or
replace the `RuleDefinition.capability` contract used by a trusted application.

## Explanatory images

A rule can carry `ExplanatoryImage` entries with localized alternative text and
an optional localized caption. Images are package-contained assets referenced by
a normalized relative path and declared media type. PNG, JPEG, WebP, and SVG are
supported.

Normalization rejects absolute paths, traversal, backslashes, extension and
media-type mismatches, duplicate image IDs, missing files, symlink escapes,
active SVG content, external SVG references, and raster signature mismatches.
Images are explanatory only and never change applicability or execution.

## Folders are cosmetic

`RuleFolder` exists for presentation and organization. Its position does not
change selector scope, rule identity, execution semantics, or trust. Consumers
may render alternative views without rewriting the rules.

## Compatibility status

The current schema version is `0.1.0` and pre-stable. See the
[roadmap](../community/roadmap.md) for the planned compatibility policy and the
[changelog](../community/changelog.md) for contract changes.
