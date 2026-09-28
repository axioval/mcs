# Schemaoberfläche

Diese genaue Referenz richtet sich an Menschen, die Software mit Axioval
verbinden. Wenn Sie nur eine Prüfung verstehen oder vorbereiten möchten,
beginnen Sie stattdessen bei den [vier Bausteinen](../guide/building-blocks.de.md).

Die Quelltextbeispiele bleiben eingeklappt, bis Sie sie bewusst öffnen.

## Module

| Modul | Zuständig für |
| --- | --- |
| `Types.pkl` | Bezeichner, semantische Versionen, lokalisierter Text, Paketmetadaten |
| `Citations.pkl` | bibliografische Quellen, Fundstellen, Zitate und Parameterziele |
| `Values.pkl` | Markierte Skalar- und Listenwerte sowie Objekt- und Eigenschaftsreferenzen |
| `Selectors.pkl` | Selektoren für Objekttyp, Eigenschaft, Eigenschaftsmuster, Klassifikation, verbundene Objekte, Disziplin, Quelle und boolesche Zusammensetzung |
| `Definitions.pkl` | Vokabulare und wiederverwendbare Fähigkeitsvorlagen |
| `RuleSets.pkl` | Konkrete Regelinstanzen und rein kosmetische Ordner |

## Paketmetadaten und Zitate

`PackageMetadata.name` und `description` verwenden `LocalizedText`. Autoren
verbinden Sprachen nicht mehr in einer Zeichenkette. Jedes Definitions- oder
Regelsatzdokument besitzt einen `sources`-Katalog. Eine Quelle enthält Art,
formale Bezeichnung, lokalisierten Titel sowie optional Herausgeber, Ausgabe,
ISO-Veröffentlichungsdatum und HTTPS-URL.

Ein `Citation` verweist auf eine Quelle und kann geordnete Fundstellen wie Teil,
Klausel, Absatz, Tabelle, Abbildung oder Seite angeben. Definitionskomponenten,
Regeln und Anforderungen können Zitate tragen. `parameterCitations` ordnet ein
Zitat ausdrücklich Parametern zu, die diese Regel tatsächlich bindet. Unbekannte
Quellen-IDs, unsichere URLs, ungültige Daten, doppelte Zitat-IDs oder Fundstellen
und unbekannte Parameterziele werden geschlossen abgelehnt.

Zitate sind ausschließlich Herkunftsmetadaten. Sie ändern weder Anwendbarkeit,
Nachweise, Auswertung, Ergebnis, Rechtswirkung noch Konformitätsaussagen.

## Definitionspaket

Ein normalisiertes Definitionsdokument hat diese Felder der obersten Ebene:

??? example "Quelltext oder Befehle anzeigen"
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

Mindestens eine wiederverwendbare Komponente muss vorhanden sein. Map-Schlüssel müssen den Komponenten-IDs entsprechen. Doppelte Komponenten-IDs über geladene Pakete hinweg werden abgelehnt.

### `ObjectTypeDefinition`

Ordnet eine stabile Axioval-Objekttyp-ID externen Schemanamen wie `IfcWall` zu. Objekttypreferenzen können festlegen, ob Untertypen akzeptiert werden.

### `PropertyDefinition`

Ordnet eine stabile Eigenschafts-ID externen Namen und einer `valueKind` zu. Mengeneigenschaften benötigen außerdem eine qualifizierte `unitDimension`. Die Eigenschaft ist von jedem Container unabhängig.

### `PropertySetDefinition`

Ordnet eine stabile Qualifizierer-ID externen Containernamen zu. Sie enthält keine Mitgliederliste und begründet keine Eigentumsbeziehung.

### `RuleDefinition`

Deklariert eine Fähigkeit und eine typisierte Parameter-Map. `referencedValueKind` ist nur für einen `propertyReference`-Parameter gültig und beschränkt den katalogisierten Typ der referenzierten Eigenschaft.

### Tabellenparameter

Ein `table`-Parameter trägt Zeilen aus Mustern und Grenzwerten in einer einzigen
Regel, etwa eine Mindestfläche je Raumtyp, statt einer Regel je Zeile. Er
deklariert seine `columns`, jede mit einer `id`, einem lokalisierten `name`,
einer optionalen `description`, einer `kind` und der Angabe, ob sie `required`
ist (die Voreinstellung):

| Spaltenart | Zellwert |
| --- | --- |
| `string` | `string` |
| `textPattern` | `string`, gelesen als Platzhaltermuster, das den ganzen Wert treffen muss: `*` beliebig viele Zeichen, `?` genau ein Zeichen, `\` maskiert das nächste Zeichen |
| `number` | `number` |
| `quantity` | `quantity`; die Spalte benötigt eine `unitDimension` |
| `integer` | `integer` |
| `boolean` | `boolean` |
| `selector` | `selector` |
| `reference` | `reference` |
| `date` | `date`, ein realer Tag in der Form `YYYY-MM-DD` |
| `dateTime` | `dateTime`, ein Zeitpunkt mit seinem UTC-Versatz |

Ein Tabellenwert ist eine Liste von Zeilen. Jede Zeile ordnet Spalten-IDs Zellen
der Art ihrer Spalte zu. Der Binder lehnt eine Zeile mit unbekannter Spalte,
einer Zelle anderer Art, einer fehlenden Pflichtzelle oder einem Textmuster ab,
das mit einem unmaskierten Backslash endet, gleich ob die Zeile in einer Regel
gebunden oder Teil des `defaultValue` ist. In Selektorzellen genannte Konzepte
müssen wie in jedem Selektor auflösbar sein. Spalten-IDs sind eindeutig,
`columns` ist für eine Tabelle Pflicht und für jede andere Art ungültig, und eine
Tabelle deklariert keine `allowedValues`. Eine leere Tabelle ist gültig.

Normalisiertes JSON lässt `columns` bei allen anderen Parametern weg, sodass
bestehende Pakete unverändert gerendert werden. Welche Zeile gilt (der erste
Treffer, der spezifischste Treffer oder jeder Treffer), legt der Vertrag der
Fähigkeit fest, nicht das Paket.

??? example "Tabellenparameter mit Voreinstellung anzeigen"
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

## Referenzwerte

=== "Objekttyp"

    ??? example "JSON anzeigen"
        ```json
        {
          "type": "objectTypeReference",
          "objectType": "axioval:example.ifc.wall",
          "includeSubtypes": true
        }
        ```

=== "Eigenschaft, lose"

    ??? example "JSON anzeigen"
        ```json
        {
          "type": "propertyReference",
          "property": "axioval:example.ifc.is-external"
        }
        ```

=== "Eigenschaft, streng"

    ??? example "JSON anzeigen"
        ```json
        {
          "type": "propertyReference",
          "property": "axioval:example.ifc.load-bearing",
          "propertySet": "axioval:example.ifc.pset-wall-common"
        }
        ```

### Attributsets

Die reservierten Sets `axioval:attributes`, `axioval:type-attributes`,
`axioval:presentation`, `axioval:material` und `axioval:body` benennen, was
eine Quelle außerhalb ihrer eigenen Eigenschaftssets angibt, etwa die Attribute
eines Objekts, seine Materialschichten oder seinen Körper. Sie sind keine
Paketkonzepte und binden an sich selbst, sodass Eigenschaftsselektoren,
Eigenschaftsreferenzen und Kategorieebenen sie ohne Eigenschaftsset-Konzept
benennen. Die Eigenschaft darin ist ein gewöhnliches Eigenschaftskonzept und
wird wie jedes andere über die Kataloge gebunden: Ein Paket deklariert
`space-number` für ein Attribut der Quelle und referenziert es in
`axioval:attributes`.

??? example "JSON anzeigen"
    ```json
    {
      "type": "propertyReference",
      "property": "axioval:example.ifc.reference",
      "propertySet": "axioval:attributes"
    }
    ```

## Datums- und Zeitpunktwerte

`date` und `dateTime` sind Wertarten von Parametern wie von
Eigenschaftskonzepten. Ihre Literale sind Zeichenketten im erweiterten
ISO-8601-Format, wie XML Schema `xs:date` und `xs:dateTime` schreibt, und der
Binder lehnt jedes Literal ab, das die prüfende Engine ablehnen würde:

- Ein `date` ist `YYYY-MM-DD`: ein tatsächlich existierender Tag des
  proleptischen gregorianischen Kalenders in den Jahren `0000` bis `9999`.
  `2024-02-29` ist daher gültig, `2026-02-29` nicht.
- Ein `dateTime` ist `YYYY-MM-DDThh:mm:ss`, ein optionaler Bruchteil mit einer
  bis neun Ziffern und ein verpflichtender UTC-Versatz, `Z` oder `±hh:mm` von
  höchstens 14 Stunden. Die Uhrzeit reicht von `00:00:00` bis `23:59:59`:
  `24:00:00` und Schaltsekunden werden abgelehnt, ebenso `-00:00`, das keinen
  Versatz angibt. Ein Zeitpunkt ohne Versatz nennt eine Uhrzeit in einer
  unbekannten Zeitzone und lässt sich nicht ordnen, er ist daher nicht
  darstellbar.

Nur ASCII-Ziffern zählen. Das Literal bleibt, wie es geschrieben ist; `Z` und
`+00:00` sind beide zulässig.

??? example "Datums- und Zeitpunktwerte anzeigen"
    ```pkl
    new Values.DateValue { value = "2026-09-27" }
    new Values.DateTimeValue { value = "2026-09-27T10:00:00.5+02:00" }
    ```

Ein Datum wird mit einem Datum nach dem Tag verglichen, ein Zeitpunkt mit einem
Zeitpunkt als Augenblick, unabhängig vom Versatz: `10:00:00+02:00` ist gleich
`08:00:00Z`. Ein Zeitpunkt wird mit einem Datum nur bei der Genauigkeit `day`
verglichen. Sie liest jeden Zeitpunkt als den Kalendertag, den er in seinem
eigenen Versatz angibt, nicht als UTC-Tag: `2026-09-27T22:30:00-05:00` liegt am
27.

Ein Eigenschaftsselektor gibt sie als `precision = "day"` an. Das Feld ist
optional, `day` ist sein einziger Wert, und es ist nur mit einem `date`- oder
`dateTime`-Wert in `value` zulässig; normalisiertes JSON lässt es weg, wenn es
nicht gesetzt ist. Mit ihm darf eine `date`-Eigenschaft mit einem
`dateTime`-Wert verglichen werden und umgekehrt; ohne es muss der Wert von der
Art der Eigenschaft sein.

??? example "Selektor anzeigen, der eine Zeitpunkteigenschaft nach dem Tag vergleicht"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.installed-at"
      operator = "lessThan"
      value = new Values.DateValue { value = "2026-09-27" }
      precision = "day"
    }
    ```

Regeldefinitionen deklarieren die Datumsparameter der
Eigenschaftsfähigkeiten (Eigenschaftsprädikat, Eigenschaftsvergleich und
Eigenschaftswert) als Parameter der Art `date` oder `dateTime`, etwa `date`,
`date_time`, `target_date` und `target_date_time`, und ihre `precision` als
`string`-Parameter mit dem einzigen Wert `day`. Ein `table`-Parameter nimmt
Spalten der Arten `date` und `dateTime`, deren Zellen wie jedes andere Datums-
oder Zeitpunktliteral geprüft werden.

## Selektoren

Selektoren sind deklarativ und werden rekursiv validiert:

- `all`
- `entityType` mit einer kanonischen Objekttyp-ID
- `property` mit kanonischer Eigenschafts-ID und optionalem Set-Qualifizierer
- `propertyPattern`, der die eigenen Set- und Eigenschaftsnamen der Quelle
  über Muster nach XML Schema abgleicht
- `classification` nach einem Code, einem Codemuster oder einem ganzen
  Klassifikationssystem
- `related`, der die über einen Beziehungspfad erreichten Objekte prüft
- `discipline`, der die Objekte von Quellen mit einer deklarierten Disziplin auswählt
- `source`, der vergleicht, was eine Quelle über sich selbst angibt, etwa die
  Anwendung, die sie geschrieben hat
- `ruleOutcome`, der danach auswählt, wie eine andere Regel des Regelsatzes ein
  Objekt beurteilt hat
- `allOf`, `anyOf` und `not`

Ein Vergleichswert auf einem Eigenschaftsselektor muss zur katalogisierten `valueKind` der referenzierten Eigenschaft passen. Die Anwesenheitsoperatoren `exists`, `isEmpty` und `isNotEmpty` lehnen einen Vergleichswert ab. Jeder andere Operator benötigt einen.

| Operator | Wert | Bedeutung |
| --- | --- | --- |
| `equals`, `notEquals` | Art der Eigenschaft | gleich oder ungleich |
| `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals` | `integer`, `number`, `quantity`, `string`, `date` oder `dateTime` | geordneter Vergleich; Datums- und Zeitpunktwerte chronologisch |
| `matches` | `string` | regulärer Ausdruck, der den ganzen Wert treffen muss |
| `like` | `string` | Platzhaltermuster, das den ganzen Wert treffen muss: `*` beliebig viele Zeichen, `?` genau ein Zeichen, `\` maskiert das nächste Zeichen |
| `contains` | `string` | der Wert enthält den Text als Teilzeichenkette |
| `oneOf`, `noneOf` | `stringList` | der Wert ist einer der aufgeführten Texte oder keiner davon; jedes Element muss ein Wert der Art der Eigenschaft sein |
| `exists` | keiner | die Eigenschaft hat einen Wert |
| `isEmpty` | keiner | die Eigenschaft ist vorhanden, aber null, leerer Text oder eine Liste aus nichts anderem; eine fehlende Eigenschaft ist nicht leer |
| `isNotEmpty` | keiner | die Eigenschaft ist mit einem Wert vorhanden; eine fehlende Eigenschaft ist kein Wert |

Zwei optionale Schalter steuern Textvergleiche, also jeden Vergleich eines
`string`-, `enum`- oder `reference`-Werts sowie die Operatoren `matches`,
`like`, `contains`, `oneOf` und `noneOf`:

- `caseSensitive: false` vergleicht ohne Rücksicht auf Groß- und
  Kleinschreibung. Voreinstellung ist `true`.
- `trim: true` entfernt Leerraum am Anfang und Ende des ermittelten
  Eigenschaftswerts vor dem Vergleich. Der deklarierte `value` wird nie
  gekürzt. Voreinstellung ist `false`.

Normalisiertes JSON lässt beide Schalter weg, solange sie ihre Voreinstellung
behalten, sodass bestehende Pakete unverändert gerendert werden. Ein von der
Voreinstellung abweichender Schalter auf einem Anwesenheitsoperator oder auf
einem Vergleich, der kein Textvergleich ist, wird abgelehnt.

??? example "Selektor mit Platzhaltern ohne Groß- und Kleinschreibung anzeigen"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.ifc.reference"
      operator = "like"
      value = new Values.StringValue { value = "EI*" }
      caseSensitive = false
      trim = true
    }
    ```

### Listenwertige Eigenschaften

Ein Eigenschaftskonzept mit der `valueKind` `stringList` oder `referenceList`
ist listenwertig: Die Anwendung kann mehrere Werte dafür ermitteln, etwa jede
Darstellungsebene (Layer) eines Objekts. Eine Liste wird nie als Ganzes
verglichen. Ein Vergleich einer listenwertigen Eigenschaft gibt einen
`quantifier` an, und sein `value` passt dann zur Art der Elemente, `string`
oder `reference`:

- `any` gilt, wenn mindestens ein Element den Vergleich erfüllt;
- `all` gilt, wenn jedes Element ihn erfüllt, und nie für eine leere Liste.

Ein einzelner Wert zählt als Liste mit einem Element, daher ist ein Quantor
auch auf einer skalaren Eigenschaft zulässig. Die Anwesenheitsoperatoren
nehmen keinen Quantor, und jeder andere Wert für `quantifier` wird abgelehnt. Normalisiertes JSON
lässt einen nicht gesetzten Quantor weg, sodass bestehende Pakete unverändert
gerendert werden.

„Jede Ebene ist vereinbart“ ist `oneOf` mit `quantifier = "all"`, „mindestens
eine Ebene ist vereinbart“ dasselbe mit `"any"`, und „keine Ebene ist
verboten“ `noneOf` mit `"all"`.

??? example "Quantifizierten Ebenenselektor anzeigen"
    ```pkl
    new Selectors.PropertySelector {
      property = "axioval:example.ifc.layers"
      operator = "oneOf"
      value = new Values.StringListValue { value { "A-WALL"; "A-DOOR" } }
      quantifier = "all"
    }
    ```

### Eigenschaftsmusterselektoren

Ein `propertyPattern`-Selektor wählt ein Objekt anhand der Eigenschaften aus,
deren Namen regulären Ausdrücken nach XML Schema entsprechen, so wie IDS
Eigenschaftssets und Eigenschaften benennt (`Pset_.*Common`).

??? example "JSON anzeigen"
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

`propertyPattern` und das optionale `propertySetPattern` passen auf den ganzen
Namen, den die Quelle angibt, nie auf ein Konzept: Sie werden nicht über die
Konzeptkataloge gebunden, ein Muster benennt also keine katalogisierte
Eigenschaft. Ohne `propertySetPattern` wird jedes Eigenschaftsset durchsucht,
nie aber ein reserviertes Set wie `axioval:attributes`, das ein
`property`-Selektor benennt.
Beide Muster sind nicht leere reguläre Ausdrücke nach XML Schema, in denen `^`
und `$` gewöhnliche Zeichen sind. Der Binder lehnt ein Muster ab, das sich nicht
kompilieren lässt, sowie die Konstrukte, die die prüfende Anwendung nicht exakt
abgleichen kann: Zeichenklassen-Subtraktion (`[a-z-[aeiou]]`), die
Namens-Escapes `\i` und `\c` sowie Block-Escapes `\p{Is…}`.

`matched` legt fest, welche der passenden Eigenschaften den Vergleich erfüllen
müssen:

- `any` gilt, wenn mindestens eine ihn erfüllt;
- `all` gilt, wenn jede ihn erfüllt.

Passt keine Eigenschaft, trifft der Selektor in beiden Fällen nicht zu. Die
Vergleichsfelder `operator`, `value`, `caseSensitive`, `trim`, `quantifier` und
`precision` vergleichen den Wert jeder passenden Eigenschaft wie bei einem
Eigenschaftsselektor. Da kein Konzept die `valueKind` der passenden Eigenschaften
deklariert, prüft der Binder den Wert nur gegen den Operator; die prüfende
Anwendung vergleicht ihn mit dem Wert jeder Eigenschaft. Normalisiertes JSON
lässt `caseSensitive` und `trim` mit ihren Standardwerten sowie ein nicht
gesetztes `propertySetPattern`, `quantifier` oder `precision` weg, sodass
bestehende Pakete unverändert gerendert werden. Der Binder lehnt jeden weiteren
Schlüssel ab.

??? example "Musterselektor über allgemeine Eigenschaftssets anzeigen"
    ```pkl
    new Selectors.PropertyPatternSelector {
      propertySetPattern = "Pset_.*Common"
      propertyPattern = "Is(External|LoadBearing)"
      matched = "all"
      operator = "equals"
      value = new Values.BooleanValue { value = true }
    }
    ```

### Verbundene Objekte

Ein `related`-Selektor wählt ein Objekt anhand der Objekte aus, die ein
Beziehungspfad `path` von ihm aus erreicht. Jeder Schritt ist `Beziehung` oder
`Beziehung:Richtung`, mit der Richtung `forward` (Standard), `backward` oder
`either`, optional gefolgt von `+`, um den Schritt ein- oder mehrmals zu gehen
und so jedes Objekt entlang der Kette der Beziehung zu erreichen, etwa
`IfcRelAggregates:backward+`. Die Schritte werden nacheinander durchlaufen und erreichen nie das
Objekt selbst. Beziehungsnamen sind die eigenen Namen der Quelle, etwa
IFC-Beziehungsentitäten, keine Konzepte; der verschachtelte `selector` nennt
Konzepte wie jeder andere Selektor und wird gegen dieselben Kataloge gebunden.
Ein Schritt darf auch eine Beziehung nennen, die die prüfende Anwendung aus der
Geometrie ableitet, `axioval:derived.<name>` mit optionalen
`;key=value`-Toleranzen, etwa `axioval:derived.adjacent-space;reach=1`, gefolgt
von einer Richtung und `+`, wie ein Kategoriepfad es erlaubt.

| `quantifier` | Wählt aus, wenn |
| --- | --- |
| `any` (Standard) | mindestens ein erreichtes Objekt passt |
| `all` | jedes erreichte Objekt passt und mindestens eines erreicht wird |
| `none` | kein erreichtes Objekt passt, auch wenn keines erreicht wird |

Normalisiertes JSON lässt den Standardwert `any` weg, und der verschachtelte
Selektor behält seine eigene Normalisierung. Der Binder lehnt einen leeren
`path`, einen Schritt mit Leerraum, einen leeren Namen, eine andere Richtung
oder eine fehlerhafte abgeleitete Beziehung sowie jeden anderen Wert für
`quantifier` ab.

??? example "Selektor für Türen in Brandwänden anzeigen"
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

### Klassifikationsselektoren

Ein `classification`-Selektor wählt die Objekte aus, die eine Klassifikation in
`system` tragen, wie ihre Quelle sie angibt. `code` nennt genau einen Code;
`codePattern` gleicht Codes über ein Muster nach XML Schema über den ganzen Code
ab, wie IDS Klassifikationsmuster schreibt (`Ss_25_.*`), und wird wie ein Muster
für Eigenschaftsnamen geprüft. Höchstens eines von beiden ist angegeben: Ohne
beide passt jede Klassifikation in `system`. `includeDescendants` trifft auch
die Codes, die die Vorfahren einer Zuordnung tragen, und benötigt einen Code
oder ein Muster.

Normalisiertes JSON lässt einen nicht gesetzten `code` oder `codePattern` weg,
sodass bestehende Pakete unverändert gerendert werden. Pkl und der Binder
lehnen `code` zusammen mit `codePattern`, `includeDescendants: true` ohne beide
sowie ein leeres oder nicht unterstütztes Muster ab.

??? example "Klassifikationsselektor mit Muster anzeigen"
    ```pkl
    new Selectors.ClassificationSelector {
      system = "uniclass"
      codePattern = "Ss_25_.*"
      includeDescendants = true
    }
    ```

### Disziplinselektoren

Ein `discipline`-Selektor wählt die Objekte der Quellen aus, die in der Prüfung
eine Disziplin vertreten, etwa `architecture` oder `structure`.

??? example "JSON anzeigen"
    ```json
    { "kind": "discipline", "value": "structure" }
    ```

Eine Disziplin gehört zu einer Quelle, nicht zu einem Objekt: Die prüfende
Anwendung deklariert sie je Quelle, daher passen alle Objekte einer Quelle oder
keines. Ein Objekt, dessen Quelle keine Disziplin deklariert, wird nicht
ausgewertet und gilt nie als Nichttreffer. So kann eine auf Disziplinen
beschränkte Regel ein Modell, das niemand zugeordnet hat, nicht bestehen.

Der `value` ist ein Token aus 1 bis 64 ASCII-Kleinbuchstaben, Ziffern, `-` oder
`_`, der mit einem Buchstaben oder einer Ziffer beginnt
(`[a-z0-9][a-z0-9_-]{0,63}`). Es ist kein Vokabular festgelegt; Namen werden
exakt verglichen, und ein Projekt einigt sich auf seine Namen wie auf seine
Regeln. Der Selektor hat genau diese beiden Schlüssel. Er darf überall stehen,
wo ein Selektor stehen darf: in `allOf`, `anyOf` und `not`, als `selector`
eines `related`-Selektors und als Wert eines selektortypisierten Parameters. Der
Binder lehnt jedes andere Token und jeden weiteren Schlüssel ab.

??? example "Kollisionsmatrix zwischen zwei Disziplinen anzeigen"
    ```pkl
    new Selectors.AllOfSelector {
      operands {
        new Selectors.EntityTypeSelector { objectType = "axioval:example.wall" }
        new Selectors.DisciplineSelector { value = "architecture" }
      }
    }
    ```

    Der selektortypisierte Parameter `counterparts` der Regel erhält dann
    `new Selectors.DisciplineSelector { value = "structure" }`.

### Quellenselektoren

Ein `source`-Selektor wählt die Objekte der Quellen aus, deren Metadatenfeld
`field` einen Vergleich erfüllt:

| `field` | Bei der Quelle |
| --- | --- |
| `fileName` | der Dateiname, aus dem die prüfende Anwendung sie geladen hat |
| `application` | der Name jeder Anwendung, die sie nach eigener Angabe geschrieben hat |
| `schema` | das deklarierte Schema, etwa `IFC4` |
| `project` | der Name des beschriebenen Projekts |
| `timestamp` | die Angabe, wann sie geschrieben wurde, wie angegeben, etwa `FILE_NAME.time_stamp` in IFC |

Quellenmetadaten sind keine Objekteigenschaft: Alle Objekte einer Quelle passen
oder keines. `operator`, `value`, `caseSensitive`, `trim` und `quantifier`
vergleichen das Feld wie ein Eigenschaftsselektor einen `string`-Wert, daher
prüft der Binder den Wert als Textvergleich und bindet kein Konzept. Ein Feld
mit mehreren Werten, etwa ein von zwei Anwendungen geschriebenes Modell,
benötigt einen `quantifier`. Ein Feld, das die Quelle als leer angibt, passt auf
nichts, wie eine fehlende Eigenschaft. Ein Feld, das die prüfende Anwendung nie
gelesen hat, wird nicht ausgewertet und gilt nie als Nichttreffer.

Normalisiertes JSON lässt `caseSensitive` und `trim` mit ihrer Voreinstellung
sowie einen nicht gesetzten `value` oder `quantifier` weg, und der Binder lehnt
jeden anderen Schlüssel ab; ein Quellenselektor nimmt keine `precision`.

??? example "Selektor für Modelle einer Anwendung anzeigen"
    ```pkl
    new Selectors.SourceSelector {
      field = "application"
      operator = "like"
      value = new Values.StringValue { value = "Modeller*" }
      caseSensitive = false
      quantifier = "any"
    }
    ```

### Regelergebnisselektoren

Ein `ruleOutcome`-Selektor wählt Objekte danach aus, wie eine andere Regel
desselben Regelsatzes sie beurteilt hat. `rule` ist die ID dieser Regel und
`outcome` ist `passed` für ein Objekt, das die Regel ausgewählt und zu dem sie
nichts berichtet hat, oder `failed` für ein Objekt, das Prüfobjekt eines ihrer
Befunde ist. Ein Objekt, das die andere Regel nicht ausgewertet hat oder bei
dem sie nicht entscheiden konnte, ob sie es auswählt, wird nicht ausgewertet
und ist nie Treffer oder Nichttreffer. Die prüfende Anwendung führt die andere
Regel zuerst aus.

Der Selektor steht überall, wo in einem Regelsatz ein Selektor steht: in einer
Anwendbarkeit, einer Zielgruppe, einem Selektorparameter oder einer
Tabellenzelle und einer Schwereüberschreibung. Der Binder prüft die exakten
Schlüssel und `outcome` sowie, dass `rule` eine Regelinstanz desselben
Regelsatzes ist, auch eine deaktivierte; eine Regel, die ihr eigenes Ergebnis
liest, und Regeln, die zusammen mit ihren [Gates](#regel-gates) gegenseitig
ihre Ergebnisse in einem Zyklus lesen, werden abgelehnt.

??? example "Selektor für die Türen anzeigen, an denen eine Türtypregel scheiterte"
    ```pkl
    new Selectors.RuleOutcomeSelector {
      rule = "door-type"
      outcome = "failed"
    }
    ```

## Umfangreiche Anwendbarkeit

Eine Regel mit mehreren Populationen verwendet ein `Applicability`-Objekt. Die
Map `groups` gibt jeder Population eine stabile lokale ID, einen lokalisierten
Namen, eine optionale Beschreibung und einen rekursiv validierten Selektor.
Anforderungen und vertrauenswürdige Host-Adapter können diese Gruppen über ihre
ID ansprechen.

Eine Regel für die Schlitz- und Durchbruchsplanung kann zum Beispiel getrennte
Gruppen für durchdrungene Bauteile, durchdringende Bauteile und Öffnungen
benennen, statt sie als eine flache Auswahl darzustellen. Map-Schlüssel müssen
den Gruppen-IDs entsprechen. Leere Gruppen-Maps, unbekannte Begriffe und
fehlerhafte Selektoren werden abgelehnt.

Bestehende Regeln dürfen weiterhin direkt einen einzelnen Selektor angeben.
Anforderungen benötigen die umfangreiche Form, weil ein flacher Selektor keine
adressierbaren Gruppen-IDs hat.

## Anforderungen

Eine `Requirement` besitzt eine stabile ID, eine lokalisierte Aussage, eine
optionale Beschreibung und eine oder mehrere `targetGroups`. Jede referenzierte
Gruppe muss in derselben Regel vorhanden sein. Anforderungs-IDs und
Gruppenreferenzen müssen eindeutig sein.

Anforderungen erklären den erwarteten Zustand. Sie führen keinen Paketcode aus
und ersetzen nicht den Vertrag `RuleDefinition.capability`, den eine
vertrauenswürdige Anwendung umsetzt.

## Erklärende Bilder

Eine Regel kann `ExplanatoryImage`-Einträge mit lokalisiertem Alternativtext und
einer optionalen lokalisierten Bildunterschrift enthalten. Bilder sind im Paket
enthaltene Dateien mit normalisiertem relativem Pfad und deklariertem Medientyp.
PNG, JPEG, WebP und SVG werden unterstützt.

Die Normalisierung lehnt absolute Pfade, Traversierung, Rückwärtsschrägstriche,
Abweichungen zwischen Erweiterung und Medientyp, doppelte Bild-IDs, fehlende
Dateien, aus dem Paket führende symbolische Links, aktive SVG-Inhalte, externe
SVG-Referenzen und falsche Raster-Signaturen ab. Bilder erklären nur und ändern
weder Anwendbarkeit noch Ausführung.

## Verfeinerungen einer Regel

Eine Fähigkeit entscheidet, was gefunden wird. Eine Regelinstanz kann zusätzlich
angeben, wie diese Befunde berichtet werden, für jede Fähigkeit gleich, sodass
keine Definition dafür einen Parameter deklariert. Das leisten drei optionale
Listen; normalisiertes JSON lässt jede leere Liste weg, sodass eine Regel ohne
sie unverändert gerendert wird, und der Binder lehnt eine leere Liste und jeden
anderen Schlüssel ab.

`severityBands` stuft einen Befund danach ab, wie weit ein gemessener Wert
seine Grenze verfehlt. Jedes Band hat eine Schwelle `below` der relativen
Abweichung `|value - bound| / |bound|` und eine `severity`: Eine Abweichung
unter der ersten Schwelle erhält die Schwere des ersten Bands, eine ab einer
Schwelle unter der nächsten die des nächsten Bands, und eine ab der letzten
Schwelle behält die eigene `severity` der Regel. Schwellen sind endliche Zahlen
über null und steigen streng an. Abgestuft werden können nur Fähigkeiten, die
eine Abweichung berichten; bei jeder anderen lehnt die prüfende Anwendung die
Bänder ab.

`severityOverrides` wählt eine Schwere nach den Objekten, die ein Befund
betrifft. Jeder Eintrag ist ein `selector` und eine `severity`; die Einträge
werden der Reihe nach gegen Prüfobjekt und verbundene Objekte des Befunds
geprüft, und der erste, dessen Selektor eines davon auswählt, entscheidet. Der
Selektor nennt Konzepte und wird wie jeder andere Selektor gegen die
Konzeptkataloge gebunden. Eine Überschreibung, die sich nicht entscheiden lässt,
lässt den Befund unausgewertet, statt seine Schwere zu setzen.

`categories` stellt der Meldung jedes Befunds verschachtelte Kategorien voran,
die äußerste zuerst, etwa `[F90] [Office]`. Jede Ebene liest `property`, ein
Eigenschaftskonzept, im optionalen `propertySet`, einem
Eigenschaftsgruppenkonzept oder einer reservierten Gruppe wie
`axioval:attributes`, am Prüfobjekt des Befunds oder, mit einem `path`, an jedem
Objekt, das der Pfad von ihm aus erreicht. Der Pfad nimmt die Schritte eines
Selektors für verbundene Objekte und darf zusätzlich abgeleitete Beziehungen
wie `axioval:derived.adjacent-space` mit ihren Toleranzen nennen. Mehrere
erreichte Werte teilen sich eine Überschrift, und kein Wert ergibt `[-]`.

??? example "Regel mit Verfeinerungen anzeigen"
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

## Regel-Gates

Eine Regelinstanz oder ein Regelordner kann ein `gate` auf eine andere Regel
desselben Regelsatzes deklarieren: die ID der anderen Regel als `rule` und eine
`condition`. Normalisiertes JSON lässt ein nicht gesetztes Gate weg, sodass
Regeln und Ordner ohne Gate unverändert gerendert werden.

| `condition` | Die Regel mit Gate läuft |
| --- | --- |
| `allIfPassed` | auf ihrer ganzen Auswahl, wenn die andere Regel bestanden hat |
| `allIfFailed` | auf ihrer ganzen Auswahl, wenn die andere Regel gescheitert ist |
| `passedObjects` | nur auf den Objekten, die die andere Regel bestanden haben |
| `failedObjects` | nur auf den Objekten, an denen die andere Regel gescheitert ist |

Ein Gate auf die ganze Regel, das nicht erfüllt ist, überspringt die Regel, die
dann nichts berichtet. Die Objektbedingungen schränken die Anwendbarkeit der
Regel ein wie ein [`ruleOutcome`-Selektor](#regelergebnisselektoren). Das Gate
eines Ordners gilt für jede Regel im Ordner und seinen Unterordnern, zusammen
mit dem eigenen Gate jeder Regel, und muss eine Regel außerhalb des Ordners
nennen.

Der Binder prüft die exakten Schlüssel und `condition` sowie, dass `rule` eine
Regelinstanz desselben Regelsatzes ist, auch eine deaktivierte, und kein
Ordner. Er lehnt eine Regel mit einem Gate auf sich selbst ab und Regeln, deren
Gates und `ruleOutcome`-Selektoren gegenseitig ihre Ergebnisse in einem Zyklus
lesen.

Eine Regelinstanz kann `auxiliary = true` deklarieren. Eine Hilfsregel läuft
nur für die Regeln, die ihr Ergebnis über ein Gate oder einen
`ruleOutcome`-Selektor lesen, und berichtet selbst keine Befunde, Tabellen oder
Zusammenfassung; was sie unentschieden lässt, bleibt in den lesenden Regeln
nicht ausgewertet. Eine solche Regel wählt etwa eine Population, die kein
Selektor exakt angibt. Normalisiertes JSON lässt `auxiliary` weg, wenn es
`false` ist, und der Binder lehnt ein ausdrückliches `false` ab. Er lehnt eine
aktivierte Hilfsregel ab, die keine aktivierte Regel des Regelsatzes über ein
Gate, das Gate eines Ordners oder einen `ruleOutcome`-Selektor liest, da ihr
Ergebnis den Bericht nie erreichen würde.

??? example "Ordner anzeigen, der nur Türen mit gescheitertem Typ prüft"
    ```pkl
    new RuleSets.RuleFolder {
      id = "door-hardware"
      name { default = "Door hardware" }
      gate { rule = "door-type"; condition = "failedObjects" }
    }
    ```

## Abgeleitete Klassifikationen

Ein Regelsatz kann `classifications` nach ID deklarieren: benannte Klassen, die
er für jedes Objekt aus geordneten Zeilen ableitet, jede ein `selector` und der
Klassenname `class`, den sie vergibt. Normalisiertes JSON lässt eine leere Map
weg, sodass Regelsätze ohne Klassifikationen unverändert gerendert werden.

| `mode` | Klasse eines Objekts |
| --- | --- |
| `firstMatch` (Voreinstellung) | die Klasse der ersten passenden Zeile, sobald jede Zeile davor sicher nicht passt: ein String |
| `allMatch` | die Klasse jeder passenden Zeile, ohne Wiederholung, in Zeilenreihenfolge, sobald jede Zeile entschieden ist: eine Liste von Strings |

Normalisiertes JSON lässt die Voreinstellung `firstMatch` weg. Ein Objekt, auf
das keine Zeile passt, hat keine Klasse, ein exaktes Fehlen. Jeder Selektor,
jede Eigenschaftsreferenz und jede Kategorieebene des Regelsatzes nennt eine
Klassifikation als Eigenschaft `id` in der reservierten Gruppe
`axioval:classification`; diese Eigenschaft bindet an kein Konzept, und ein
Selektor, der eine `allMatch`-Klassifikation vergleicht, gibt einen
`quantifier` an.

Der Binder prüft die exakten Schlüssel, dass jeder Map-Schlüssel seiner nicht
leeren `id` gleicht, `mode` sowie, dass `rows` nicht leer und keine `class`
leer ist. Zeilenselektoren werden wie jeder andere Selektor gegen die
Konzeptkataloge gebunden und enthalten nie einen `ruleOutcome`-Selektor, da
Klassen abgeleitet werden, bevor eine Regel läuft; Klassifikationen dürfen
einander nennen, aber nie in einem Zyklus. Eine Eigenschaft in
`axioval:classification` muss eine Klassifikation nennen, die der Regelsatz
deklariert.

??? example "Klassifikation und einen Selektor darauf anzeigen"
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

    // Überall, wo ein Selektor steht:
    new Selectors.PropertySelector {
      propertySet = "axioval:classification"
      property = "space-use"
      operator = "equals"
      value = new Values.StringValue { value = "office" }
    }
    ```

## Gemessene Werte

Die reservierte Gruppe `axioval:measured` nennt Werte, die die prüfende
Anwendung am Körper eines Objekts misst, statt sie aus einer Quelle zu lesen:

| Name | Wert |
| --- | --- |
| `extent_x`, `extent_y` | die Ausdehnung entlang der x- oder y-Achse der Welt, eine Länge |
| `extent_z` | die Höhe, eine Länge |
| `bottom`, `top` | die Höhenlage des tiefsten und höchsten Punkts, eine Länge |
| `area` | die Grundrissfläche, Überlappungen einmal gezählt |
| `volume` | das umschlossene Volumen |
| `x`, `y`, `z` | die Weltkoordinaten des Einfügepunkts, eine Länge |
| `level_height` | die Höhe eines Geschosses bis zum nächsten Geschoss, eine Länge, wie die Quelle sie angibt |
| `bottom_above_level;path=<steps>` | die Unterkante über der einen Ebene, die der Pfad erreicht, eine Länge |
| `boundary_area;kind=<kind>[;plane=<metres>]` | die Begrenzungsfläche eines Raums gegen Elemente der Quellenart `kind` oder eines Untertyps |

Zwei Namen nehmen nach dem Namen Parameter, durch `;` getrennte
`key=value`-Paare, die Teil des Eigenschaftsnamens sind. `bottom_above_level`
benötigt `path`, die durch `,` getrennten Schritte, wie ein Selektor für
verbundene Objekte sie schreibt, `Relationship[:forward|backward|either][+]`,
etwa `IfcRelContainedInSpatialStructure:backward`. `boundary_area` benötigt
`kind` und nimmt optional `plane`, eine Zahl von Metern von mindestens null.

Selektoren, Eigenschaftsreferenzen und Kategorieebenen nennen sie in dieser
Gruppe, abgeglichen ohne Rücksicht auf ASCII-Groß- und Kleinschreibung und
umgebenden Leerraum; sie binden an kein Konzept. Der Binder lehnt dort jeden
anderen Namen ab, ebenso einen fehlenden benötigten Parameter, einen
fehlerhaften Schritt oder `plane`, einen doppelt angegebenen und jeden anderen
Parameter. Ein
Selektor vergleicht einen gemessenen Wert mit einer `quantity`. Ein Wert, den
die Anwendung nur innerhalb eines Intervalls bestimmt, etwa an einem
triangulierten Körper, lässt ein Objekt unausgewertet, wenn das Intervall die
Grenze überspannt.

??? example "Selektor für Objekte niedriger als 50 mm anzeigen"
    ```pkl
    new Selectors.PropertySelector {
      propertySet = "axioval:measured"
      property = "extent_z"
      operator = "lessThan"
      value = new Values.QuantityValue { value = 0.05; unit = "m" }
    }
    ```

## Ordner sind kosmetisch

`RuleFolder` dient Darstellung und Organisation. Seine Position ändert weder Selektorumfang, Regelidentität, Ausführungssemantik noch Vertrauen. Verbraucher können alternative Ansichten darstellen, ohne die Regeln umzuschreiben. Das [Gate](#regel-gates) eines Ordners ist die einzige Ausnahme: Es steht am Ordner, gilt aber für jede Regel darin, als hätte jede Regel es ebenfalls deklariert.

## Kompatibilitätsstatus

Die aktuelle Schemaversion ist `0.1.0` und noch nicht stabil. Die geplante Kompatibilitätspolitik steht in der [Roadmap](../community/roadmap.de.md), Vertragsänderungen im [Changelog](../community/changelog.de.md).
