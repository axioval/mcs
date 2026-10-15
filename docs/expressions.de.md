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
| Werte | `literal`, `null`, `property`, `parameter`, `derived`, `lookup`, `interpolate`, `lookup2`, `catalogue` |
| Wahrheit | `not`, `and`, `or`, `implies`, `xor`, `isDefined`, `isUndefined` |
| Vergleich | `compare`, `between`, `oneOf`, `noneOf` |
| Auswahl | `if`, `coalesce` |
| Arithmetik | `add`, `subtract`, `multiply`, `divide`, `negate`, `abs`, `min`, `max`, `round`, `floor`, `ceil`, `sqrt`, `inUnit` |
| Winkel und Neigungen | `sin`, `cos`, `tan`, `atan2`, `convertSlope` |
| Mitglieder | `aggregate`, `argmin`, `argmax`, `pairs`, `previous`, `next` |
| andere Regeln | `ruleOutcome`, `selected`, `findingCount`, `deviation` |
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
  `table`-Parameters, deren Schlüsselspalten zu `keys` passen. `interpolate`
  und `lookup2` lesen zwischen den Zeilen einer Tabelle; siehe
  [Tabellen](#tabellen).
- Ein `catalogue` entnimmt einen Wert einem Katalog, den der Host neben dem
  Modell liefert, etwa die Wärmeleitfähigkeit eines Baustoffs; siehe
  [Kataloge](#kataloge).
- `compare` nimmt einen Operator `operator`: `equals`, `notEquals`,
  `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals`,
  `like`, `matches` oder `contains`. `caseSensitive: false` ignoriert die
  Groß- und Kleinschreibung. `between` schließt beide Grenzen ein, solange
  `lowInclusive` oder `highInclusive` nicht `false` ist.
- `if` liefert das `then` des ersten Zweigs in `branches`, dessen `when` gilt,
  sonst sein `else`.
- `convertSlope` drückt eine Neigung `from` einer der Formen `ratio`,
  `percent` und `angle` `to` in einer anderen aus.
- `floor` und `ceil` runden ab oder auf ganze Zahlen, oder mit einer
  optionalen Schrittweite `step` in der Einheit des Operanden auf deren
  Vielfache, wie eine Norm die Richtung vorschreibt: `ceil(4.2, 1)` sind 5
  Stellplätze, `floor(0.987 m, 0.01 m)` ist `0.98 m`.
- `inUnit` drückt seinen `operand` in einer geschriebenen Einheit `unit`
  derselben Dimension aus, etwa `mm`, `cm` oder `%`: derselbe Wert, in dieser
  Einheit angezeigt. Eine `sum` über kein Mitglied ist null in der Einheit
  ihrer Mitglieder.
- `aggregate` berechnet `count`, `sum`, `min`, `max`, `average`, `any`, `all`,
  `none` oder `distinctCount` über Mitglieder, die es `over` einen
  Beziehungspfad `path`, die abgeleitete Gruppe `group` einer Gruppierung,
  einen `selector` oder eine gemessene Mitgliederliste `measured` wie `steps`
  erreicht. Ein optionaler Selektor `where` filtert die Mitglieder, und `value`
  wird für jedes ausgewertet; eine Zählung nimmt kein `value`, jede andere
  Funktion braucht eines. Im `value` eines Aggregats über gemessene Mitglieder
  nennt die reservierte Menge `axioval:member` die Felder jedes Mitglieds.
- `argmin` und `argmax` wählen das Mitglied, dessen `by`, eine Zahl, am
  kleinsten oder größten ist, und lesen sein `value`; so bezieht sich eine
  Regel auf das maßgebende Mitglied: die steilste Dachfläche, den längsten
  Rettungsweg. Sie erreichen ihre Mitglieder mit `over` und filtern sie mit
  `where` wie ein Aggregat und werten `by` und `value` für jedes Mitglied aus;
  über gemessenen Mitgliedern lesen beide `axioval:member`. Überlappen sich
  Intervalle, wird jedes Mitglied gewählt, das das Extrem sein kann, und der
  Wert ist der, in dem sie übereinstimmen, sonst ungeprüft, nie einer nach
  Reihenfolge herausgegriffen.
- `pairs` setzt jedes Mitglied einer geordneten Folge mit dem vorhergehenden
  in Beziehung: aufeinanderfolgende Steigungen, nach Höhe gestapelte
  Geschosse. Es erreicht seine Mitglieder mit `over` und filtert sie mit
  `where` wie ein Aggregat, ordnet sie aufsteigend nach `by`, einer Zahl wie
  einer Station, einer Höhe oder einer laufenden Nummer, und wendet seine
  Aggregatfunktion `function` auf `value` an, das einmal je
  aufeinanderfolgendem Paar mit dem späteren Mitglied im Blick ausgewertet
  wird. In diesem `value` liest `previous` seinen `operand` vom früheren
  Mitglied und `next` vom späteren, sodass sich ein Paar in beiden Richtungen
  schreiben lässt; ein `count` nimmt kein `value` und zählt ein Paar weniger
  als Mitglieder. Ein Paar, dessen Reihenfolge die Intervalle von `by` offen
  lassen, bleibt ungeprüft und wird nie nach einer Vermutung geordnet.
- `ruleOutcome`, `findingCount` und `deviation` lesen, wie eine andere Regel
  desselben Regelsatzes das betrachtete Objekt beurteilt hat, und `selected`,
  ob sie es ausgewählt hat. `ruleOutcome` ist `null` für ein Objekt, das die
  Regel nicht ausgewählt hat; sichern Sie es daher mit `selected` ab:
  `implies(selected(r), ruleOutcome(r))`.

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

??? example "Aufeinanderfolgende Steigungen mit höchstens 5 mm Unterschied anzeigen"
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

## Wahrheit und fehlende Werte

Eine Wahrheit ist wahr, falsch, `null` oder ungeprüft. `null` ist ein Wert, den
die Quelle als fehlend angibt; ungeprüft heißt, dass ein Wert nicht gelesen oder
ein Ergebnis nicht entschieden werden konnte. Die prüfende Anwendung verwendet
Kleenes dreiwertige Logik über wahr, falsch und `null` und hält ungeprüft davon
getrennt:

- Ein Vergleich mit `null` ist `null`, nie falsch; `not(x == 5)` und `x != 5`
  gelten daher nie für ein Objekt, das kein `x` angibt. `noneOf` ist stets
  `not oneOf`.
- `and` ist falsch, sobald ein Operand falsch ist, und `or` wahr, sobald einer
  wahr ist; sonst entscheidet ein ungeprüfter Operand, danach `null`.
- `any`, `all` und `none` lesen ein Mitglied mit `null` als unbekannt, und
  `sum`, `min`, `max`, `average` und `distinctCount` sind `null`, sobald der
  Wert eines Mitglieds es ist.
- Eine Anforderung, die `null` ist, ist ein Befund wegen fehlender Angaben, nie
  ein Bestehen. Nur `isDefined`, `isUndefined` und `coalesce` lesen `null` als
  Wert: `implies(isDefined(x), test)` hebt eine Anforderung auf, wo `x` fehlt,
  `and(isDefined(x), test)` verlangt einen Wert, und `coalesce(flag, false)`
  liest ein fehlendes Kennzeichen als falsch.

Das Buch der Engine führt die Wahrheitstafel jedes Operators auf.

## Tabellen

Die `table`-Parameter einer Regel werden auf drei Arten gelesen. `lookup`
wählt die spezifischste Zeile, deren Schlüsselzellen zu `keys` passen.
`interpolate` liest die Zelle `column` an einem Schlüssel `key` der numerischen
Spalte `keyColumn`, linear interpoliert zwischen den beiden Zeilen, deren
Schlüssel ihn einschließen, wie Normtabellen Werte an Stützstellen angeben: die
Zeilen `2.0 -> 10` und `3.0 -> 20` ergeben 14 bei 2,4. Ein Schlüssel vor der
ersten oder hinter der letzten Zeile ist ungeprüft und wird nie extrapoliert,
es sei denn, `clamp: true` erklärt den Wert der nächsten Randzeile für gültig.

`lookup2` liest eine Tabelle mit zwei Schlüsseln, eine Zelle je Zeile, etwa
eine Betondeckung nach Expositionsklasse und Bauteildicke. Es sucht `rowKey`
in `rowKeyColumn` und `columnKey` in `columnKeyColumn` genau, oder interpoliert
mit `interpolateRow` oder `interpolateColumn` linear entlang dieser
numerischen Schlüsselspalte, bilinear, wenn beide gesetzt sind. Eine Zelle, die
keine Zeile angibt, ist ungeprüft und wird nie von einer entfernteren Zeile
geborgt; `clamp` gilt für beide Schlüssel.

??? example "Betondeckung an der Spannweite einer Platte anzeigen"
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

Der Binder verlangt, dass die Tabelle ein `table`-Parameter ist, den die Regel
bindet oder vorgibt, dass jede genannte Spalte eine ihrer Spalten ist, dass
eine interpolierte Schlüsselspalte eine `integer`-, `number`- oder
`quantity`-Spalte ist und dass auch die gelesene Spalte `column` eine ist,
sobald ein Schlüssel interpoliert wird. Ob die Einheit eines Schlüssels zu
seiner Spalte passt, prüft die prüfende Anwendung.

## Kataloge

Modelle lassen Baustoff- und Produktdaten oft weg oder nennen einen Baustoff
nur beim Namen: Eine Wand gibt den Namen ihres Baustoffs an, nicht seine
Wärmeleitfähigkeit. Ein Regelsatz deklariert die Form eines Katalogs mit
solchen Daten in `catalogues`, nach ID, und der Host liefert seine Einträge zur
Prüfzeit neben dem Modell, als CSV-Datei oder als ein Blatt einer
`.xlsx`-Arbeitsmappe, mit der Version des Katalogs. So dient ein Regelpaket
jeder Katalogausgabe, und das Paket gibt keine Einträge an.

Ein `catalogue`-Knoten liest den Eintrag des Katalogs `catalogue`, dessen
Schlüssel genau gleich `key` ist, einem Text, und entnimmt ihm den Wert der
Spalte `column`. Der Wert ist die Angabe des Katalogs, belegt mit ID, Version,
Dateiprüfsumme und Eintrag des Katalogs, nie die des Modells. Eine leere Zelle
ist `null`, ebenso ein Schlüssel `null`; ein Schlüssel, den kein Eintrag hat,
und ein Katalog, den der Host nicht geliefert hat, lassen das Objekt
ungeprüft und geben ihm nie einen Vorgabewert.

??? example "Wärmeleitfähigkeit eines Baustoffs aus einem Katalog anzeigen"
    ```pkl
    catalogues {
      ["materials"] {
        id = "materials"
        name { default = "Baustoffe" }
        key = "name"
        columns {
          new { id = "name"; header = "Baustoff"; kind = "string" }
          new { id = "lambda"; header = "λ"; kind = "quantity"; unit = "W/(m·K)" }
        }
      }
    }
    ```

    ```pkl
    new Expressions.CatalogueExpression {
      catalogue = "materials"
      key = new Expressions.PropertyExpression {
        propertySet = "axioval:example.material"
        property = "axioval:example.material.name"
      }
      column = "lambda"
      label = "thermal conductivity"
    }
    ```

Der Binder verlangt, dass der Katalog deklariert ist und `column` eine seiner
Spalten außer der Schlüsselspalte ist, die die Einträge benennt. Dass `key`
ein Text ist, prüft die prüfende Anwendung.

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
gesetzte Felder, die Vorgabe `true` von `caseSensitive`, `lowInclusive` und
`highInclusive` sowie die Vorgabe `false` von `clamp`, `interpolateRow` und
`interpolateColumn` weg. Die `keys` eines Lookups sind nach Spalten-ID
geordnet. Ein `floor` oder `ceil` ohne `step` und ein Regelsatz ohne `values`
werden bytegleich ausgegeben.

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
  Knoten enthält oder Aggregate, `argmin`, `argmax` und `pairs` tiefer als
  zwei Ebenen in `value`, `by` oder `where` ineinander schachtelt;
- ein Aggregat oder `pairs`, dessen `value` nicht zu seiner Funktion passt, ein
  `where` über gemessenen Mitgliedern, eine unbekannte gemessene
  Mitgliederliste und `axioval:member` außerhalb des `value` eines solchen
  Aggregats oder des `by` und `value` eines solchen `argmin`, `argmax` oder
  `pairs`;
- ein `previous` oder `next` irgendwo außer im `value` eines `pairs`: nicht in
  dessen `by` oder `where`, nicht in einem anderen `previous` oder `next` und
  nicht in einem Aggregat, `argmin`, `argmax` oder `pairs`, das in diesem
  `value` verschachtelt ist und seine eigenen Mitglieder liest;
- eine Eigenschaft, die weder ein deklariertes Konzept noch ein Name einer
  abgeleiteten Menge ist, eine unbekannte Gruppierung, Relation oder
  Klassifikation und einen `derived`-Wert, den der Regelsatz nicht deklariert;
- einen `parameter`, `lookup`, `interpolate` oder `lookup2` außerhalb eines
  Ausdrucksparameters oder mit einem Parameter, den die Regel weder bindet noch
  vorgibt, einer Tabellenspalte, die es nicht gibt, einem Parameter, der kein
  einzelner Wert ist, oder einer nicht numerischen Spalte, entlang der oder
  aus der interpoliert wird;
- ein `catalogue`, das einen Katalog nennt, den der Regelsatz nicht
  deklariert, eine Spalte, die der Katalog nicht deklariert, oder seine
  Schlüsselspalte;
- ein Regelergebnis einer Regel außerhalb des Regelsatzes, eine Regel, die ihr
  eigenes Ergebnis liest, Regeln, die einander im Kreis lesen, und jedes
  Regelergebnis in einem abgeleiteten Wert, einer Klassifikation, Gruppierung
  oder Relation; sowie
- abgeleitete Werte, die einander im Kreis lesen.

Ein Ausdruckswert wird nur für einen Parameter mit `kind = "expression"`
angenommen.
