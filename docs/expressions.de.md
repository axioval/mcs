# Mit Ausdrücken rechnen

Manche Anforderungen sind kein einzelner Vergleich. Eine Rampe darf höchstens
6 % steil sein, also ihre Steigungshöhe geteilt durch ihre Lauflänge. Eine
Platte braucht mehr Betondeckung, wenn sie vorgespannt ist. Ein Ausdruck
beschreibt eine solche Rechnung als Daten: einen kleinen Baum aus Werten und
Operationen, den die prüfende Anwendung für jedes Objekt auswertet.

Ausdrücke führen niemals Paketcode aus. Die Sprache kennt keine Schleifen, keine
Rekursion und keine eigenen Funktionen, deshalb endet jeder Ausdruck. Die
prüfende Anwendung wertet ihn mit einer vertrauenswürdigen Fähigkeit aus, die
sie bereits implementiert.

!!! note "Nicht normatives Beispiel"
    Das Rampenbeispiel auf dieser Seite dient dem Lernen. Sein Grenzwert stammt
    aus keiner Norm. Das vollständige Paket liegt in
    [`examples/expressions`](https://github.com/axioval/mcs/tree/main/examples/expressions).

## Wo ein Ausdruck steht

| Ort | Wirkung | Liest Regelparameter |
| --- | --- | --- |
| Wert eines `expression`-Parameters | die Fähigkeit wertet ihn für jedes ausgewählte Objekt aus | ja |
| `expression`-Selektor | wählt die Objekte, für die er gilt | nein |
| abgeleiteter Wert in `values` des Regelsatzes | benennt einen Wert einmal für alle Regeln | nein |

Eine Definition deklariert einen Parameter mit `kind = "expression"`. Eine Regel
bindet ihn mit `Expressions.ExpressionValue`; normalisiert lautet er
`type: "expression"` mit dem Ausdruck als `value`.

??? example "Regelvorlage mit Ausdruck anzeigen"
    ```pkl
    ["requirement"] = new Definitions.ParameterDefinition {
      id = "requirement"
      name = new Types.LocalizedText { default = "Anforderung" }
      kind = "expression"
    }
    ```

## Die Bausteine

Jeder Knoten trägt eine Art `kind` und optional ein `label`, unter dem Befunde
ihn statt seiner ausgeschriebenen Form nennen.

| Gruppe | Arten |
| --- | --- |
| Werte | `literal`, `null`, `property`, `parameter`, `derived`, `lookup` |
| Wahrheit | `not`, `and`, `or`, `implies`, `xor`, `isDefined`, `isUndefined` |
| Vergleich | `compare`, `between`, `oneOf`, `noneOf` |
| Auswahl | `if`, `coalesce` |
| Arithmetik | `add`, `subtract`, `multiply`, `divide`, `negate`, `abs`, `min`, `max`, `round`, `floor`, `ceil`, `sqrt` |
| Winkel und Neigungen | `sin`, `cos`, `tan`, `atan2`, `convertSlope` |
| Mitglieder | `aggregate` |
| andere Regeln | `ruleOutcome`, `findingCount`, `deviation` |
| Text | `concat`, `length`, `lower`, `upper`, `trim` |

- Ein `literal` enthält einen skalaren Wert in seiner Parameterwertform:
  `boolean`, `integer`, `number`, `quantity`, `string`, `enum`, `date` oder
  `dateTime`. Zahlen sind endlich. `Expressions.EnumLiteralValue` schreibt
  einen Aufzählungswert so, wie eine Quelle ihn angibt, etwa `NOTDEFINED`.
- Ein `property` nennt ein Eigenschaftskonzept mit optionalem genauen
  `propertySet` oder einen Namen einer abgeleiteten Menge: `axioval:measured`,
  `axioval:classification`, `axioval:group` oder `axioval:value` für einen
  abgeleiteten Wert. `of: "subject"` liest innerhalb eines Aggregats das von
  der Regel geprüfte Objekt.
- Ein `parameter` liest einen skalaren Parameter, den die Regel bindet oder
  vorgibt. Ein `lookup` liest die Zelle `column` der spezifischsten Zeile eines
  `table`-Parameters, deren Schlüsselspalten zu `keys` passen.
- `compare` nimmt einen Operator `operator`: `equals`, `notEquals`,
  `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals`,
  `like`, `matches` oder `contains`. `caseSensitive: false` ignoriert die
  Groß- und Kleinschreibung. `between` schließt beide Grenzen ein, solange
  `lowInclusive` oder `highInclusive` nicht `false` ist.
- `if` liefert das `then` des ersten Zweigs in `branches`, dessen `when` gilt,
  sonst sein `else`.
- `convertSlope` drückt eine Neigung `from` einer der Formen `ratio`,
  `percent` und `angle` `to` in einer anderen aus.
- `aggregate` berechnet `count`, `sum`, `min`, `max`, `average`, `any`, `all`,
  `none` oder `distinctCount` über Mitglieder, die es `over` einen
  Beziehungspfad `path`, die abgeleitete Gruppe `group` einer Gruppierung,
  einen `selector` oder eine gemessene Mitgliederliste `measured` wie `steps`
  erreicht. Ein optionaler Selektor `where` filtert die Mitglieder, und `value`
  wird für jedes ausgewertet; eine Zählung nimmt kein `value`, jede andere
  Funktion braucht eines. Im `value` eines Aggregats über gemessene Mitglieder
  nennt die reservierte Menge `axioval:member` die Felder jedes Mitglieds.
- `ruleOutcome`, `findingCount` und `deviation` lesen, wie eine andere Regel
  desselben Regelsatzes das betrachtete Objekt beurteilt hat.

??? example "Anforderung anzeigen, die eine abgeleitete Neigung mit einem Parameter vergleicht"
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

## Abgeleitete Werte

Ein Regelsatz benennt einen Wert einmal in `values`, und jede Regel, jeder
Selektor und jeder andere Wert kann ihn verwenden. Jeder hat einen lokalisierten
`name`, eine optionale `description` und eine `expression`. Ein `derived`-Knoten
nennt ihn, ebenso eine Eigenschaft der reservierten Menge `axioval:value`. Ein
Wert darf andere Werte verwenden, aber nie im Kreis. Er liest keinen
Regelparameter und kein Regelergebnis, denn Werte werden abgeleitet, bevor
irgendeine Regel läuft.

??? example "Abgeleitete Neigung in Prozent anzeigen"
    ```pkl
    values {
      ["slope_percent"] {
        name = new Types.LocalizedText { default = "Neigung in Prozent" }
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

## Ausdrucksselektoren

`Expressions.ExpressionSelector` wählt die Objekte, für die sein Ausdruck, ein
Wahrheitswert, gilt. Falsch und `null` wählen nicht aus; ein Wert, der sich
nicht entscheiden lässt, lässt das Objekt unbewertet und überspringt es nie. Er
steht überall, wo ein Selektor stehen kann, und liest Eigenschaften, gemessene
und abgeleitete Werte, aber nie die Parameter einer Regel.

??? example "Rampen anzeigen, die Steigungshöhe und Lauflänge angeben"
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

## Normalisiertes JSON

Normalisiertes JSON schreibt die Felder jedes Knotens in der Reihenfolge, in
der die prüfende Anwendung sie schreibt, das `label` zuletzt, und lässt nicht
gesetzte Felder sowie die Vorgabe `true` von `caseSensitive`, `lowInclusive`
und `highInclusive` weg. Die `keys` eines Lookups sind nach Spalten-ID
geordnet. Ein Regelsatz ohne `values` wird bytegleich ausgegeben.

Das Repository hält die goldenen Ausdrucksfixtures der prüfenden Anwendung, eine
je Art, in `tests/fixtures/expression`, jede mit einem Pkl-Modul, das sie
schreibt. Jedes Modul muss seine Fixture bytegenau ausgeben. Jede Fixture muss
außerdem als Ausdrucksparameter einer Regel in einem Paket gebunden werden, das
die von ihr genannten `ex:`-Konzepte deklariert, und aus einer gepackten
`.mcs`-Datei unverändert zurückkommen, bytegenau in der kanonischen Form des
Transports: sortierte Schlüssel und kompakte Trennzeichen, die Form, in der
`.mcs` normalisiertes JSON speichert.

## Was der Binder ablehnt

Pkl prüft die Form jedes Knotens. Der Binder lehnt danach unter anderem ab:

- eine unbekannte Art oder ein unbekanntes Feld, eine leere Operandenliste
  oder leere `branches`, ein leeres `label` oder einen leeren Namen, ein
  Literal, das kein einzelner endlicher skalarer Wert ist, und eine
  ausgeschriebene Vorgabe;
- einen Ausdruck, der tiefer als 64 Ebenen verschachtelt ist, mehr als 2.048
  Knoten enthält oder Aggregate tiefer als zwei Ebenen schachtelt;
- ein Aggregat, dessen `value` nicht zu seiner Funktion passt, ein `where` über
  gemessenen Mitgliedern, eine unbekannte gemessene Mitgliederliste und
  `axioval:member` außerhalb des `value` eines solchen Aggregats;
- eine Eigenschaft, die weder ein deklariertes Konzept noch ein Name einer
  abgeleiteten Menge ist, eine unbekannte Gruppierung, Relation oder
  Klassifikation und einen `derived`-Wert, den der Regelsatz nicht deklariert;
- einen `parameter` oder `lookup` außerhalb eines Ausdrucksparameters oder mit
  einem Parameter, den die Regel weder bindet noch vorgibt, einer
  Tabellenspalte, die es nicht gibt, oder einem Parameter, der kein einzelner
  Wert ist;
- ein Regelergebnis einer Regel außerhalb des Regelsatzes, eine Regel, die ihr
  eigenes Ergebnis liest, Regeln, die einander im Kreis lesen, und jedes
  Regelergebnis in einem abgeleiteten Wert, einer Klassifikation, Gruppierung
  oder Relation; sowie
- abgeleitete Werte, die einander im Kreis lesen.

Ein Ausdruckswert wird nur für einen Parameter mit `kind = "expression"`
angenommen.
