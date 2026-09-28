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
| `Selectors.pkl` | object type, property, property-pattern, classification, related-object, discipline, source, boolean-composition selectors |
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
| `date` | `date`, a real day written `YYYY-MM-DD` |
| `dateTime` | `dateTime`, an instant with its UTC offset |

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

## Dates and date-times

`date` and `dateTime` are value kinds of parameters and property concepts
alike. Their literals are ISO 8601 extended strings, as XML Schema writes
`xs:date` and `xs:dateTime`, and the binder refuses any literal the checking
engine would refuse:

- A `date` is `YYYY-MM-DD`: a real day of the proleptic Gregorian calendar in
  the years `0000` to `9999`, so `2024-02-29` is valid and `2026-02-29` is not.
- A `dateTime` is `YYYY-MM-DDThh:mm:ss`, an optional fraction of one to nine
  digits, and a required UTC offset, `Z` or `±hh:mm` of at most 14 hours. The
  time of day runs from `00:00:00` to `23:59:59`: `24:00:00` and leap seconds
  are refused, and so is `-00:00`, which states no offset. A date-time without
  an offset names a wall-clock time in an unknown zone and cannot be ordered, so
  it is not representable.

Only ASCII digits count. The literal is kept as written; `Z` and `+00:00` are
both accepted.

??? example "Show date and date-time values"
    ```pkl
    new Values.DateValue { value = "2026-09-27" }
    new Values.DateTimeValue { value = "2026-09-27T10:00:00.5+02:00" }
    ```

A date compares with a date by day, and a date-time with a date-time as an
instant, whatever the offsets: `10:00:00+02:00` equals `08:00:00Z`. A date-time
compares with a date only at `day` precision, which reads every date-time as the
calendar day it states in its own offset, not the UTC day:
`2026-09-27T22:30:00-05:00` is on the 27th.

A property selector states it as `precision = "day"`. The field is optional,
`day` is its only value, and it is accepted only with a `date` or `dateTime`
`value`; normalized JSON omits it when unset. With it, a `date` property may be
compared with a `dateTime` value and the other way round; without it, the value
must be of the property's kind.

??? example "Show a selector comparing a date-time property by day"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.installed-at"
      operator = "lessThan"
      value = new Values.DateValue { value = "2026-09-27" }
      precision = "day"
    }
    ```

Rule definitions declare the date parameters of the property capabilities
(property predicate, property comparison, and property value) as parameters of
kind `date` or `dateTime`, such as `date`, `date_time`, `target_date`, and
`target_date_time`, and their `precision` as a `string` parameter whose only
value is `day`. A `table` parameter takes `date` and `dateTime` columns, whose
cells are checked like any other date or date-time literal.

## Selectors

Selectors are declarative and recursively validated:

- `all`
- `entityType` using a canonical object-type ID
- `property` using a canonical property ID and optional set qualifier
- `propertyPattern`, matching the source's own property-set and property
  names by XML Schema patterns
- `classification`, by a code, a code pattern, or a whole classification
  system
- `related`, testing the objects a relationship path reaches
- `discipline`, selecting the objects of sources that declare a discipline
- `source`, comparing what a source states about itself, such as the
  application that wrote it
- `ruleOutcome`, selecting by how another rule of the ruleset judged an object
- `allOf`, `anyOf`, and `not`

A comparison value on a property selector must match the referenced property's
catalogued `valueKind`. The presence operators `exists`, `isEmpty`, and
`isNotEmpty` reject a comparison value; every other operator requires one.

| Operator | Value | Meaning |
| --- | --- | --- |
| `equals`, `notEquals` | the property's kind | equal or not equal |
| `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals` | `integer`, `number`, `quantity`, `string`, `date`, or `dateTime` | ordered comparison; dates and date-times chronologically |
| `matches` | `string` | regular expression matching the whole value |
| `like` | `string` | wildcard pattern matching the whole value: `*` any run of characters, `?` one character, `\` escapes the next character |
| `contains` | `string` | the value contains the text as a substring |
| `oneOf`, `noneOf` | `stringList` | the value is, or is not, one of the listed texts; each element must be a value of the property's kind |
| `exists` | none | the property has a value |
| `isEmpty` | none | the property is present but null, blank text, or a list of nothing else; an absent property is not empty |
| `isNotEmpty` | none | the property is present with a value; an absent property is not a value |

Two optional flags tune text comparisons, meaning any comparison of a `string`,
`enum`, or `reference` value and the operators `matches`, `like`, `contains`,
`oneOf`, and `noneOf`:

- `caseSensitive: false` compares without regard to case. The default is `true`.
- `trim: true` strips leading and trailing whitespace from the resolved property
  value before comparing. The declared `value` is never trimmed. The default is
  `false`.

Normalized JSON omits both flags when they keep their defaults, so existing
packages render unchanged. Setting either away from its default on a presence
operator or on a comparison that is not text is rejected.

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
on a scalar property. The presence operators take no quantifier, and any other
`quantifier` value is rejected. Normalized JSON omits an unset quantifier, so
existing packages render unchanged.

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

### Property-pattern selectors

A `propertyPattern` selector selects an object by the properties whose names
match XML Schema regular expressions, as IDS names property sets and
properties (`Pset_.*Common`).

??? example "Show JSON"
    ```json
    {
      "kind": "propertyPattern",
      "propertySetPattern": "Pset_.*Common",
      "propertyPattern": "Is(External|LoadBearing)",
      "matched": "all",
      "operator": "equals",
      "value": { "type": "boolean", "value": true }
    }
    ```

`propertyPattern` and the optional `propertySetPattern` match the whole name the
source states, never a concept: they are not bound through the concept catalogs,
so a pattern names no catalogued property. Without `propertySetPattern` every
property set is searched. Both patterns are non-empty XML Schema regular
expressions, in which `^` and `$` are ordinary characters. The binder rejects a
pattern that does not compile and the constructs the checking application
cannot match exactly: character-class subtraction (`[a-z-[aeiou]]`), the `\i`
and `\c` name escapes, and `\p{Is…}` block escapes.

`matched` states which of the matching properties must satisfy the comparison:

- `any` holds when at least one does;
- `all` holds when every one does.

A selector no property matches is no match under either. The comparison fields
`operator`, `value`, `caseSensitive`, `trim`, `quantifier`, and `precision`
compare each matched property's value as on a property selector. Since no
concept declares the matched properties' `valueKind`, the binder checks the
value against the operator only, and the checking application compares it with
each property's own value. Normalized JSON omits `caseSensitive` and `trim` at
their defaults and an unset `propertySetPattern`, `quantifier`, or `precision`,
so existing packages render unchanged. The binder rejects any other key.

??? example "Show a pattern selector over common property sets"
    ```pkl
    new Selectors.PropertyPatternSelector {
      propertySetPattern = "Pset_.*Common"
      propertyPattern = "Is(External|LoadBearing)"
      matched = "all"
      operator = "equals"
      value = new Values.BooleanValue { value = true }
    }
    ```

### Related selectors

A `related` selector selects an object by the objects a relationship `path`
reaches from it. Each step is `Relationship` or `Relationship:direction`, with
direction `forward` (the default), `backward`, or `either`. The steps are
walked one after another and never reach the object itself. Relationship names
are the source's own names, such as IFC relationship entity names, not concepts;
the nested `selector` names concepts like any other selector and binds against
the same catalogs.

| `quantifier` | Selects when |
| --- | --- |
| `any` (default) | at least one reached object matches |
| `all` | every reached object matches, and at least one is reached |
| `none` | no reached object matches, also when none is reached |

Normalized JSON omits the default `any`, and the nested selector keeps its own
normalization. The binder rejects an empty `path`, a step with whitespace, an
empty name, or another direction, and any other `quantifier` value.

??? example "Show a selector for doors in compartment walls"
    ```pkl
    new Selectors.AllOfSelector {
      operands {
        new Selectors.EntityTypeSelector { objectType = "axioval:example.door" }
        new Selectors.RelatedSelector {
          path { "IfcRelFillsElement:backward"; "IfcRelVoidsElement:backward" }
          selector = new Selectors.PropertySelector {
            property = "axioval:example.compartmentation"
            operator = "equals"
            value = new Values.BooleanValue { value = true }
          }
        }
      }
    }
    ```

### Classification selectors

A `classification` selector selects the objects carrying a classification in
`system`, as their source states it. `code` names one code exactly;
`codePattern` matches codes by an XML Schema pattern over the whole code, as IDS
writes classification patterns (`Ss_25_.*`), and is checked like a
property-name pattern. At most one of them is given: with neither, any
classification in `system` matches. `includeDescendants` also matches the codes
an assignment's ancestors carry and needs a code or a pattern.

Normalized JSON omits an unset `code` or `codePattern`, so existing packages
render unchanged. Pkl and the binder reject `code` together with
`codePattern`, `includeDescendants: true` with neither, and an empty or
unsupported pattern.

??? example "Show a classification selector by pattern"
    ```pkl
    new Selectors.ClassificationSelector {
      system = "uniclass"
      codePattern = "Ss_25_.*"
      includeDescendants = true
    }
    ```

### Discipline selectors

A `discipline` selector selects the objects of the sources that play a
discipline in the check, such as `architecture` or `structure`.

??? example "Show JSON"
    ```json
    { "kind": "discipline", "value": "structure" }
    ```

A discipline belongs to a source, not to an object: the checking application
declares one per source, so every object of a source matches or none does. An
object whose source declares no discipline is not evaluated, never a non-match,
so a discipline-scoped rule cannot pass over a model nobody classified.

The `value` is a token of 1 to 64 lowercase ASCII letters, digits, `-`, or `_`,
starting with a letter or digit (`[a-z0-9][a-z0-9_-]{0,63}`). No vocabulary is
fixed; names compare exactly, and a project agrees on its names as it agrees on
its rules. The selector has exactly these two keys. It may appear wherever a
selector may: inside `allOf`, `anyOf`, and `not`, as a related selector's
`selector`, and as a selector-typed parameter value. The binder rejects any
other token and any other key.

??? example "Show a clash matrix between two disciplines"
    ```pkl
    new Selectors.AllOfSelector {
      operands {
        new Selectors.EntityTypeSelector { objectType = "axioval:example.wall" }
        new Selectors.DisciplineSelector { value = "architecture" }
      }
    }
    ```

    The rule's selector-typed `counterparts` parameter then takes
    `new Selectors.DisciplineSelector { value = "structure" }`.

### Source selectors

A `source` selector selects the objects of the sources whose metadata `field`
satisfies a comparison:

| `field` | The source's |
| --- | --- |
| `fileName` | file name the checking application loaded it from |
| `application` | name of every application it states wrote it |
| `schema` | declared schema, such as `IFC4` |
| `project` | name of the project it describes |

Source metadata is not an object fact: every object of a source matches or none
does. `operator`, `value`, `caseSensitive`, `trim`, and `quantifier` compare the
field as a property selector compares a `string` value, so the binder checks
the value as a text comparison and binds no concept. A field holding several
values, such as a model written by two applications, needs a `quantifier`. A
field the source states empty matches nothing, as an absent property does. A
field the checking application never read is not evaluated, never a non-match.

Normalized JSON omits `caseSensitive` and `trim` at their defaults and an unset
`value` or `quantifier`, and the binder rejects any other key; a source selector
takes no `precision`.

??? example "Show a selector for models written by one application"
    ```pkl
    new Selectors.SourceSelector {
      field = "application"
      operator = "like"
      value = new Values.StringValue { value = "Modeller*" }
      caseSensitive = false
      quantifier = "any"
    }
    ```

### Rule-outcome selectors

A `ruleOutcome` selector selects objects by how another rule of the same
ruleset judged them. `rule` is that rule's ID and `outcome` is `passed`, for an
object the rule selected and reported nothing about, or `failed`, for an object
that is the subject of one of its findings. An object the other rule left not
evaluated, or could not decide whether it selected, is not evaluated, never a
match or a non-match. The checking application runs the other rule first.

The selector goes wherever a selector goes in a ruleset: an applicability, a
target group, a selector parameter or table cell, and a severity override. The
binder checks exact keys and the `outcome`, and that `rule` is a rule instance
of the same ruleset, also a disabled one; a rule reading its own outcome, and
rules reading one another's outcomes in a cycle, together with their
[gates](#rule-gates), are rejected.

??? example "Show a selector for the doors a door-type rule failed"
    ```pkl
    new Selectors.RuleOutcomeSelector {
      rule = "door-type"
      outcome = "failed"
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

## Rule refinements

A capability decides what is found. A rule instance may additionally say how
those findings are reported, the same way for every capability, so no
definition declares a parameter for it. Three optional lists do so; normalized
JSON omits each when empty, so a rule declaring none renders unchanged, and the
binder rejects an empty list and any other key.

`severityBands` grades a finding by how far a measured value misses its bound.
Each band has a `below` threshold of the relative deviation
`|value - bound| / |bound|` and a `severity`: a deviation below the first
threshold takes the first band's severity, one from a threshold below the next
takes the next band's, and one at or beyond the last threshold keeps the rule's
own `severity`. Thresholds are finite numbers above zero and ascend strictly.
Only capabilities that report a deviation can be graded; the checking
application refuses bands on any other.

`severityOverrides` chooses a severity by the objects a finding involves. Each
entry is a `selector` and a `severity`; the entries are tried in order against
the finding's subject and related objects, and the first whose selector selects
one of them decides. The selector names concepts and binds against the concept
catalogs like any other selector. An override that cannot be decided leaves the
finding not evaluated rather than defaulting its severity.

`categories` heads each finding's message with nested categories, outermost
first, such as `[F90] [Office]`. Each level reads `property`, a property
concept, in the optional `propertySet`, a property-set concept or a reserved
set such as `axioval:attributes`, on the finding's subject or, with a `path`, on
every object the path reaches from it. The path takes the steps of a related
selector and may also name derived relationships, such as
`axioval:derived.adjacent-space`, with their tolerances. Several reached values
share one heading and no value heads `[-]`.

??? example "Show a rule with refinements"
    ```pkl
    severity = "error"
    severityBands {
      new { below = 0.05; severity = "info" }
      new { below = 0.2; severity = "warning" }
    }
    severityOverrides {
      new {
        selector = new Selectors.PropertySelector {
          property = "axioval:example.load-bearing"
          operator = "equals"
          value = new Values.BooleanValue { value = true }
        }
        severity = "error"
      }
    }
    categories {
      new { property = "axioval:example.fire-rating" }
      new {
        propertySet = "axioval:attributes"
        property = "axioval:example.name"
        path { "axioval:derived.adjacent-space" }
      }
    }
    ```

## Rule gates

A rule instance, or a rule folder, may declare a `gate` on another rule of the
same ruleset: the other rule's ID as `rule` and a `condition`. Normalized JSON
omits an unset gate, so rules and folders without one render unchanged.

| `condition` | The gated rule runs |
| --- | --- |
| `allIfPassed` | on its whole selection, if the other rule passed |
| `allIfFailed` | on its whole selection, if the other rule failed |
| `passedObjects` | on the objects the other rule passed only |
| `failedObjects` | on the objects the other rule failed only |

A whole-rule gate that does not hold skips the rule, which then reports
nothing. The object conditions narrow the rule's applicability as a
[`ruleOutcome` selector](#rule-outcome-selectors) does. A folder's gate applies
to every rule in the folder and its subfolders, together with each rule's own
gate, and must name a rule outside the folder.

The binder checks exact keys and the `condition`, and that `rule` is a rule
instance of the same ruleset, also a disabled one, not a folder. It rejects a
rule gated on itself and rules whose gates and `ruleOutcome` selectors read one
another's outcomes in a cycle.

??? example "Show a folder checked only on doors that failed their type"
    ```pkl
    new RuleSets.RuleFolder {
      id = "door-hardware"
      name { default = "Door hardware" }
      gate { rule = "door-type"; condition = "failedObjects" }
    }
    ```

## Derived classifications

A ruleset may declare `classifications`, by ID: named classes it derives for
every object from ordered rows, each a `selector` and the `class` name it
assigns. Normalized JSON omits an empty map, so rulesets without
classifications render unchanged.

| `mode` | An object's class |
| --- | --- |
| `firstMatch` (default) | the class of the first matching row, once every row before it surely does not match: a string |
| `allMatch` | every matching row's class, distinct, in row order, once every row is decided: a list of strings |

Normalized JSON omits the default `firstMatch`. An object no row matches has no
class, an exact absence. Every selector, property reference, and category level
of the ruleset names a classification as the property `id` in the reserved set
`axioval:classification`; that property binds to no concept, and a selector
comparing an `allMatch` classification states a `quantifier`.

The binder checks exact keys, that each map key equals its non-blank `id`, the
`mode`, and that `rows` is non-empty and no `class` is blank. Row selectors
bind against the concept catalogs like any other selector and never contain a
`ruleOutcome` selector, since classes are derived before any rule runs;
classifications may name one another, but never in a cycle. A property in
`axioval:classification` must name a classification the ruleset declares.

??? example "Show a classification and a selector naming it"
    ```pkl
    classifications {
      ["space-use"] {
        id = "space-use"
        name { default = "Space use" }
        rows {
          new {
            selector = new Selectors.PropertySelector {
              property = "axioval:example.name"
              operator = "like"
              value = new Values.StringValue { value = "Office*" }
            }
            `class` = "office"
          }
        }
      }
    }

    // Anywhere a selector goes:
    new Selectors.PropertySelector {
      propertySet = "axioval:classification"
      property = "space-use"
      operator = "equals"
      value = new Values.StringValue { value = "office" }
    }
    ```

## Folders are cosmetic

`RuleFolder` exists for presentation and organization. Its position does not
change selector scope, rule identity, execution semantics, or trust. Consumers
may render alternative views without rewriting the rules. A folder's
[gate](#rule-gates) is the one exception: it is stated on the folder but applies
to each rule in it, as if each rule declared it too.

## Compatibility status

The current schema version is `0.1.0` and pre-stable. See the
[roadmap](../community/roadmap.md) for the planned compatibility policy and the
[changelog](../community/changelog.md) for contract changes.
