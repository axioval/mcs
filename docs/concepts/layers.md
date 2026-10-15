# How Axioval fits together

This page opens the booklet's four ideas and shows what sits behind each one.
The simple picture remains the same: shared names, reusable check recipes,
completed checks, and a bundle that carries them safely. Technical names appear
only where a tool builder needs them.

<div class="diagram-frame" markdown>

<picture class="responsive-diagram">
  <source media="(max-width: 44rem)" srcset="../../assets/images/building-blocks-mobile.svg">
  <img src="../../assets/images/building-blocks.svg" alt="The dictionary, recipe, filled card, and bundle used by Axioval">
</picture>

</div>

## 1. Vocabulary

A definition package can declare three independent concept catalogs:

| Concept | Purpose | Example |
| --- | --- | --- |
| `ObjectTypeDefinition` | Reusable model-object type | IFC `IfcWall` |
| `PropertyDefinition` | Reusable property identity and value kind | boolean `LoadBearing` |
| `PropertySetDefinition` | Optional external container qualifier | `Pset_WallCommon` |

Each concept has a stable qualified ID and may have verified `ExternalName`
bindings. The stable ID is what rules reference; adapters map only authenticated
bindings to supported model schemas. Project-local concepts remain explicitly
local.

!!! important
    `PropertySetDefinition` does **not** list or own properties. A property may
    appear in multiple external containers. Container membership becomes
    normative only when a selector or `PropertyReferenceValue` names a set.

## 2. Template

A `RuleDefinition` declares:

- a stable definition ID;
- a stable `capability` that applications explicitly implement; and
- typed parameter definitions.

??? example "Show the Pkl template"
    ```pkl
    ["axioval:example.boolean-property-equals"] = new Definitions.RuleDefinition {
      id = "axioval:example.boolean-property-equals"
      capability = "axioval:capability.property-value-equals"
      name = new Types.LocalizedText { default = "Boolean property equals" }
      parameters {
        ["property"] = new Definitions.ParameterDefinition {
          id = "property"
          name = new Types.LocalizedText { default = "Property" }
          kind = "propertyReference"
          referencedValueKind = "boolean"
        }
        ["expected"] = new Definitions.ParameterDefinition {
          id = "expected"
          name = new Types.LocalizedText { default = "Expected" }
          kind = "boolean"
        }
      }
    }
    ```

`referencedValueKind` closes a subtle type hole: this boolean template cannot be
bound to a string property.

A template may also fix a parameter with `fixed = true`. Every instance then
takes the parameter's `defaultValue` and may not state its own, so packages
built on the same template check the same thing. Changing a fixed parameter
means forking the definition; see the
[schema reference](../reference/schema.md#ruledefinition).

## 3. Instance

A `RuleInstance` binds a known definition to concrete values. Its applicability
can be one selector or named target groups, while requirements state what must
hold for those groups. Optional explanatory images make the intent easier to
understand but never affect execution. Instances are policy, the ABox-like
layer, and belong in external ruleset repositories. This MCS repository
contains them only under `examples/`.

## 4. Package and normalization

`axioval.json` statically identifies the package and every definition entrypoint.
Only after all entrypoints are repository-confined and all candidate JSON is
semantically bound does the output become normalized interchange.

A `ruleset` package delivers a rule set; a `definitions` package publishes
definitions only, such as a library of rule templates. A rule set names the
definition packages it binds by ID, and a host resolves them from the
definitions packages it has installed.

<div class="diagram-frame" markdown>

![A package is inspected, opened safely, checked completely, and handed to a compatible tool](../assets/images/trust-path.svg)

</div>

## What Axioval does own

<ul class="scope-list scope-list--included">
  <li>Shared, stable names for building facts</li>
  <li>Typed, reusable descriptions of checks</li>
  <li>Declarative filled checks that can be shared as data</li>
  <li>A package contract that rejects incomplete or inconsistent input</li>
</ul>

## What Axioval deliberately does not own

<ul class="scope-list scope-list--excluded">
  <li>Opening model files or following IFC relationships</li>
  <li>Calculating geometry</li>
  <li>Running executable rule logic supplied by a package</li>
  <li>Replacing an application's trusted internal model</li>
  <li>Trusting a package merely because of who owns its repository</li>
</ul>

Axioval describes meaning at the exchange boundary. Each application remains in
control of model access, algorithms, execution, and trust decisions.
