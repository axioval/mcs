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
| values | `literal`, `null`, `property`, `parameter`, `derived`, `lookup`, `interpolate`, `lookup2` |
| truth | `not`, `and`, `or`, `implies`, `xor`, `isDefined`, `isUndefined` |
| comparison | `compare`, `between`, `oneOf`, `noneOf` |
| choice | `if`, `coalesce` |
| arithmetic | `add`, `subtract`, `multiply`, `divide`, `negate`, `abs`, `min`, `max`, `round`, `floor`, `ceil`, `sqrt`, `inUnit` |
| angles and slopes | `sin`, `cos`, `tan`, `atan2`, `convertSlope` |
| members | `aggregate`, `argmin`, `argmax`, `pairs`, `previous`, `next` |
| other rules | `ruleOutcome`, `selected`, `findingCount`, `deviation` |
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
  parameter whose key columns match `keys`. `interpolate` and `lookup2` read
  between a table's rows; see [Tables](#tables).
- `compare` takes an `operator`: `equals`, `notEquals`, `lessThan`,
  `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals`, `like`, `matches`,
  or `contains`. `caseSensitive: false` folds case. `between` is inclusive
  unless `lowInclusive` or `highInclusive` is `false`.
- `if` takes the `then` of the first of its `branches` whose `when` holds, else
  its `else`.
- `convertSlope` restates a slope `from` one of `ratio`, `percent`, and
  `angle` `to` another.
- `floor` and `ceil` round down or up to whole numbers, or with an optional
  `step` of the operand's unit to its multiples, as a norm prescribes the
  direction: `ceil(4.2, 1)` is 5 parking spaces, `floor(0.987 m, 0.01 m)` is
  `0.98 m`.
- `inUnit` restates its `operand` in a written `unit` of the same dimension,
  such as `mm`, `cm`, or `%`: the same value, shown in that unit. A `sum`
  over no member is zero in its members' unit.
- `aggregate` computes `count`, `sum`, `min`, `max`, `average`, `any`, `all`,
  `none`, or `distinctCount` over members it reaches `over` a relationship
  `path`, the derived `group` of a grouping, a `selector`, or a `measured`
  member list such as `steps`. An optional `where` selector filters the
  members, and `value` is evaluated for each; a count takes no `value`, every
  other function needs one. Inside the `value` of an aggregate over measured
  members, the reserved set `axioval:member` names each member's fields.
- `argmin` and `argmax` choose the member whose `by`, a number, is least or
  greatest and read its `value`, so a rule refers to the decisive member: the
  steepest roof face, the longest escape route. They range `over` members and
  filter them with `where` as an aggregate does, and evaluate `by` and `value`
  with each member in scope; over measured members both read `axioval:member`.
  Where intervals overlap, every member that may be the extreme is chosen, and
  the value is the one they agree on, otherwise not evaluated, never one
  picked by order.
- `pairs` relates each member of an ordered sequence to the one before it:
  consecutive risers, storeys stacked by elevation. It ranges `over` members
  and filters them with `where` as an aggregate does, orders them by `by`
  ascending, a number such as a station, an elevation, or a sequence number,
  and applies its aggregate `function` to `value`, evaluated once per
  consecutive pair with the later member in scope. Within that `value`,
  `previous` reads its `operand` of the earlier member and `next` of the later
  one, so a pair can be written either way; a `count` takes no `value` and
  counts one pair fewer than the members. A pair whose order the intervals of
  `by` leave undecided is not evaluated, never ordered by a guess.
- `ruleOutcome`, `findingCount`, and `deviation` read how another rule of the
  same ruleset judged the object in scope, and `selected` whether it selected
  it. `ruleOutcome` is `null` for an object the rule did not select, so guard
  it with `selected`: `implies(selected(r), ruleOutcome(r))`.

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

??? example "Show consecutive risers differing by at most 5 mm"
    ```pkl
    ["requirement"] = new Expressions.ExpressionValue {
      value = new Expressions.PairsExpression {
        `function` = "all"
        over = new Expressions.PathSource { path { "IfcRelAggregates:forward" } }
        by = new Expressions.PropertyExpression {
          propertySet = "ex:pset-stair-flight-common"
          property = "ex:riser-sequence"
        }
        value = new Expressions.CompareExpression {
          operator = "lessThanOrEquals"
          left = new Expressions.AbsExpression {
            operand = new Expressions.SubtractExpression {
              left = new Expressions.NextExpression {
                operand = new Expressions.PropertyExpression {
                  propertySet = "ex:pset-stair-flight-common"
                  property = "ex:riser-height"
                }
              }
              right = new Expressions.PreviousExpression {
                operand = new Expressions.PropertyExpression {
                  propertySet = "ex:pset-stair-flight-common"
                  property = "ex:riser-height"
                }
              }
            }
          }
          right = new Expressions.LiteralExpression {
            value = new Values.QuantityValue { value = 5.0; unit = "mm" }
          }
        }
        label = "consecutive risers"
      }
    }
    ```

## Truth and absent values

A truth is true, false, `null`, or not evaluated. `null` is a value the source
states as absent; not evaluated means a value could not be read or a result
cannot be decided. The checking application uses Kleene's three-valued logic
over true, false, and `null`, with not evaluated kept apart:

- A comparison with `null` is `null`, never false, so `not(x == 5)` and
  `x != 5` never hold for an object that states no `x`. `noneOf` is always
  `not oneOf`.
- `and` is false when any operand is false, and `or` true when any is true;
  otherwise an operand not evaluated decides, then `null`.
- `any`, `all`, and `none` read a `null` member as unknown, and `sum`, `min`,
  `max`, `average`, and `distinctCount` are `null` when a member's value is.
- A requirement that is `null` is a missing-information finding, never a pass.
  Only `isDefined`, `isUndefined`, and `coalesce` read `null` as a value: write
  `implies(isDefined(x), test)` to lift a requirement where `x` is absent,
  `and(isDefined(x), test)` to require a value, or `coalesce(flag, false)` to
  read an absent flag as false.

The engine's book lists the truth table of every operator.

## Tables

A rule's `table` parameters are read three ways. `lookup` selects the most
specific row whose key cells match its `keys`. `interpolate` reads the `column`
cell at a `key` of the numeric `keyColumn`, interpolated linearly between the
two rows whose keys bracket it, as norm tables state values at grid points:
rows `2.0 -> 10` and `3.0 -> 20` give 14 at 2.4. A key beyond the first or
last row is not evaluated, never extrapolated, unless `clamp: true` declares
that the nearest end row's value applies.

`lookup2` reads a two-key table, one cell per row, such as a cover by exposure
class and thickness. It matches `rowKey` in `rowKeyColumn` and `columnKey` in
`columnKeyColumn` exactly, or with `interpolateRow` or `interpolateColumn`
interpolates linearly along that numeric key column; bilinearly when both are
set. A cell no row states is not evaluated, never borrowed from a farther row,
and `clamp` applies to both keys.

??? example "Show a cover read at a slab's span"
    ```pkl
    new Expressions.InterpolateExpression {
      table = "cover_by_span"
      keyColumn = "span"
      key = new Expressions.PropertyExpression {
        property = "axioval:example.slab.span"
      }
      column = "cover"
      clamp = true
    }
    ```

The binder requires the table to be a `table` parameter the rule binds or
defaults, every named column to be one of its columns, an interpolated key
column to be an `integer`, `number`, or `quantity` column, and the `column`
read to be one too when any key is interpolated. The checking application
checks that a key's unit matches its column's.

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
writes them, its `label` last, and omits unset fields, the defaults `true`
of `caseSensitive`, `lowInclusive`, and `highInclusive`, and the defaults
`false` of `clamp`, `interpolateRow`, and `interpolateColumn`. A lookup's
`keys` are ordered by column ID. A `floor` or `ceil` without a `step` and a
ruleset without `values` render byte-identically.

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
  or nesting aggregates, `argmin`, `argmax`, and `pairs` more than two deep
  within one another's `value`, `by`, or `where`;
- an aggregate or `pairs` whose `value` does not match its function, a `where`
  on measured members, an unknown measured member list, and `axioval:member`
  outside the `value` of a measured aggregate or the `by` and `value` of a
  measured `argmin`, `argmax`, or `pairs`;
- a `previous` or `next` anywhere but within the `value` of a `pairs`: not in
  its `by` or `where`, not in another `previous` or `next`, and not within an
  aggregate, `argmin`, `argmax`, or `pairs` nested in that `value`, which reads
  its own members;
- a property that is no declared concept or derived-set name, an unknown
  grouping, relation, or classification, and a `derived` value the ruleset
  does not declare;
- a `parameter`, `lookup`, `interpolate`, or `lookup2` outside an expression
  parameter, or naming a parameter the rule neither binds nor defaults, a
  table column it lacks, a parameter that is no single value, or a
  non-numeric column it interpolates along or reads interpolated;
- a rule outcome naming a rule outside the ruleset, a rule reading its own
  outcome, rules reading one another in a cycle, and any rule outcome in a
  derived value, classification, grouping, or relation; and
- derived values reading one another in a cycle.

An expression value is accepted only for a parameter of `kind = "expression"`.
