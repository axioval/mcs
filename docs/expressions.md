# Compute with expressions

Some requirements are not a single comparison. A ramp may be no steeper than
6 %, which is its rise divided by its run. A slab needs more cover when it is
prestressed. An expression states such a calculation as data: a small tree of
values and operations that the checking application evaluates for each object.

Expressions never run package code. The language has no loops, no recursion,
and no functions of your own, so every expression finishes. The checking
application evaluates it with a trusted capability it already implements.

!!! note "Non-normative example"
    The ramp example on this page is instructional. Its limit is taken from no
    standard. The complete package is in
    [`examples/expressions`](https://github.com/axioval/mcs/tree/main/examples/expressions).

## Where an expression goes

| Place | What it does | Reads rule parameters |
| --- | --- | --- |
| an `expression` parameter value | the capability evaluates it for each selected object | yes |
| an `expression` selector | selects the objects for which it holds | no |
| a derived value in the ruleset's `values` | names a value once for every rule | no |

A definition declares a parameter of `kind = "expression"`. A rule binds it with
`Expressions.ExpressionValue`; its normalized form is `type: "expression"` with
the expression as `value`.

??? example "Show an expression rule template"
    ```pkl
    ["requirement"] = new Definitions.ParameterDefinition {
      id = "requirement"
      name = new Types.LocalizedText { default = "Requirement" }
      kind = "expression"
    }
    ```

## The building blocks

Every node is tagged by `kind` and may carry a `label`, the name findings use
for it instead of its rendered form.

| Group | Kinds |
| --- | --- |
| values | `literal`, `null`, `property`, `parameter`, `derived`, `lookup` |
| truth | `not`, `and`, `or`, `implies`, `xor`, `isDefined`, `isUndefined` |
| comparison | `compare`, `between`, `oneOf`, `noneOf` |
| choice | `if`, `coalesce` |
| arithmetic | `add`, `subtract`, `multiply`, `divide`, `negate`, `abs`, `min`, `max`, `round`, `floor`, `ceil`, `sqrt` |
| angles and slopes | `sin`, `cos`, `tan`, `atan2`, `convertSlope` |
| members | `aggregate` |
| other rules | `ruleOutcome`, `findingCount`, `deviation` |
| text | `concat`, `length`, `lower`, `upper`, `trim` |

- A `literal` holds one scalar value in its parameter value form: `boolean`,
  `integer`, `number`, `quantity`, `string`, `enum`, `date`, or `dateTime`.
  Numbers are finite. `Expressions.EnumLiteralValue` writes an enumeration
  value as a source states it, such as `NOTDEFINED`.
- A `property` names a property concept, with an optional exact `propertySet`,
  or a name of a derived set: `axioval:measured`, `axioval:classification`,
  `axioval:group`, or `axioval:value` for a derived value. `of: "subject"`
  reads the rule's checked object inside an aggregate.
- A `parameter` reads a scalar parameter the rule binds or defaults. A
  `lookup` reads the `column` cell of the most specific row of a `table`
  parameter whose key columns match `keys`.
- `compare` takes an `operator`: `equals`, `notEquals`, `lessThan`,
  `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals`, `like`, `matches`,
  or `contains`. `caseSensitive: false` folds case. `between` is inclusive
  unless `lowInclusive` or `highInclusive` is `false`.
- `if` takes the `then` of the first of its `branches` whose `when` holds, else
  its `else`.
- `convertSlope` restates a slope `from` one of `ratio`, `percent`, and
  `angle` `to` another.
- `aggregate` computes `count`, `sum`, `min`, `max`, `average`, `any`, `all`,
  `none`, or `distinctCount` over members it reaches `over` a relationship
  `path`, the derived `group` of a grouping, a `selector`, or a `measured`
  member list such as `steps`. An optional `where` selector filters the
  members, and `value` is evaluated for each; a count takes no `value`, every
  other function needs one. Inside the `value` of an aggregate over measured
  members, the reserved set `axioval:member` names each member's fields.
- `ruleOutcome`, `findingCount`, and `deviation` read how another rule of the
  same ruleset judged the object in scope.

??? example "Show a requirement comparing a derived slope with a parameter"
    ```pkl
    ["requirement"] = new Expressions.ExpressionValue {
      value = new Expressions.CompareExpression {
        operator = "lessThanOrEquals"
        left = new Expressions.DerivedExpression {
          name = "slope_percent"
          label = "slope"
        }
        right = new Expressions.ParameterExpression {
          name = "maximum_slope"
          label = "steepest slope"
        }
      }
    }
    ```

## Derived values

A ruleset names a value once in `values` and every rule, selector, and other
value can use it. Each has a localized `name`, an optional `description`, and an
`expression`. A `derived` node names it, as does a property of the reserved set
`axioval:value`. A value may use other values, never in a cycle. It reads no
rule parameter and no rule's outcome, because values are derived before any
rule runs.

??? example "Show a derived slope in percent"
    ```pkl
    values {
      ["slope_percent"] {
        name = new Types.LocalizedText { default = "Slope in percent" }
        expression = new Expressions.ConvertSlopeExpression {
          operand = new Expressions.DivideExpression {
            left = new Expressions.PropertyExpression {
              property = "axioval:example.expressions.rise"
            }
            right = new Expressions.PropertyExpression {
              property = "axioval:example.expressions.run"
            }
            label = "rise over run"
          }
          from = "ratio"
          to = "percent"
        }
      }
    }
    ```

## Expression selectors

`Expressions.ExpressionSelector` selects the objects for which its expression,
a truth, holds. False and `null` do not select; a value that cannot be decided
leaves the object not evaluated, never skipped. It goes wherever a selector goes
and reads properties, measured values, and derived values, never a rule's
parameters.

??? example "Show ramps that state both rise and run"
    ```pkl
    new Selectors.AllOfSelector {
      operands {
        new Selectors.EntityTypeSelector {
          objectType = "axioval:example.expressions.ramp"
        }
        new Expressions.ExpressionSelector {
          expression = new Expressions.AndExpression {
            operands {
              new Expressions.IsDefinedExpression {
                operand = new Expressions.PropertyExpression {
                  property = "axioval:example.expressions.rise"
                }
              }
              new Expressions.IsDefinedExpression {
                operand = new Expressions.PropertyExpression {
                  property = "axioval:example.expressions.run"
                }
              }
            }
          }
        }
      }
    }
    ```

## Normalized JSON

Normalized JSON writes each node's fields in the order the checking application
writes them, its `label` last, and omits unset fields and the defaults `true`
of `caseSensitive`, `lowInclusive`, and `highInclusive`. A lookup's `keys` are
ordered by column ID. A ruleset without `values` renders byte-identically.

The repository keeps the checking application's golden expression fixtures,
one per kind, in `tests/fixtures/expression` with a Pkl module authoring each.
Every module must render its fixture byte for byte. Every fixture must also
bind as a rule's expression parameter, in a package declaring the `ex:`
concepts it names, and come back from a packed `.mcs` file unchanged, byte for
byte in the transport's canonical form: sorted keys and compact separators,
the form `.mcs` stores normalized JSON in.

## What the binder refuses

Pkl checks each node's shape. The binder then refuses, among others:

- an unknown `kind` or field, an empty operand list or `branches`, a blank
  `label` or name, a literal that is not one finite scalar value, and a stated
  default flag;
- an expression nesting deeper than 64 levels, holding more than 2,048 nodes,
  or nesting aggregates more than two deep;
- an aggregate whose `value` does not match its function, a `where` on
  measured members, an unknown measured member list, and `axioval:member`
  outside a measured aggregate's `value`;
- a property that is no declared concept or derived-set name, an unknown
  grouping, relation, or classification, and a `derived` value the ruleset
  does not declare;
- a `parameter` or `lookup` outside an expression parameter, or naming a
  parameter the rule neither binds nor defaults, a table column it lacks, or a
  parameter that is no single value;
- a rule outcome naming a rule outside the ruleset, a rule reading its own
  outcome, rules reading one another in a cycle, and any rule outcome in a
  derived value, classification, grouping, or relation; and
- derived values reading one another in a cycle.

An expression value is accepted only for a parameter of `kind = "expression"`.
