# Expression example

This instructional, non-production package computes a value once and checks
it with an expression rule:

- `definitions.pkl` declares a ramp, its rise and run, and a rule template
  whose `requirement` parameter is an expression evaluated by the trusted
  capability `axioval:capability.expression`;
- `ruleset.pkl` derives `slope_percent`, the rise over the run restated as a
  percentage, selects ramps stating both with an `expression` selector, and
  requires the derived slope to stay at or below the rule's `maximum_slope`.

The limit is illustrative and taken from no standard. Evaluate the
normalized representations:

```bash
pkl eval -f json definitions.pkl
pkl eval -f json ruleset.pkl
```
