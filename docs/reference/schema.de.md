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
| `Selectors.pkl` | Selektoren für Objekttyp, Eigenschaft, Klassifikation, verbundene Objekte und boolesche Zusammensetzung |
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
`string`-Parameter mit dem einzigen Wert `day`. Datumsspalten in
`table`-Parametern werden nicht unterstützt.

## Selektoren

Selektoren sind deklarativ und werden rekursiv validiert:

- `all`
- `entityType` mit einer kanonischen Objekttyp-ID
- `property` mit kanonischer Eigenschafts-ID und optionalem Set-Qualifizierer
- `classification`
- `related`, der die über einen Beziehungspfad erreichten Objekte prüft
- `allOf`, `anyOf` und `not`

Ein Vergleichswert auf einem Eigenschaftsselektor muss zur katalogisierten `valueKind` der referenzierten Eigenschaft passen. `exists` lehnt einen Vergleichswert ab. Jeder andere Operator benötigt einen.

| Operator | Wert | Bedeutung |
| --- | --- | --- |
| `equals`, `notEquals` | Art der Eigenschaft | gleich oder ungleich |
| `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals` | `integer`, `number`, `quantity`, `string`, `date` oder `dateTime` | geordneter Vergleich; Datums- und Zeitpunktwerte chronologisch |
| `matches` | `string` | regulärer Ausdruck, der den ganzen Wert treffen muss |
| `like` | `string` | Platzhaltermuster, das den ganzen Wert treffen muss: `*` beliebig viele Zeichen, `?` genau ein Zeichen, `\` maskiert das nächste Zeichen |
| `contains` | `string` | der Wert enthält den Text als Teilzeichenkette |
| `oneOf`, `noneOf` | `stringList` | der Wert ist einer der aufgeführten Texte oder keiner davon; jedes Element muss ein Wert der Art der Eigenschaft sein |
| `exists` | keiner | die Eigenschaft hat einen Wert |

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
Voreinstellung abweichender Schalter auf `exists` oder auf einem Vergleich, der
kein Textvergleich ist, wird abgelehnt.

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
auch auf einer skalaren Eigenschaft zulässig. `exists` nimmt keinen Quantor,
und jeder andere Wert für `quantifier` wird abgelehnt. Normalisiertes JSON
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

### Verbundene Objekte

Ein `related`-Selektor wählt ein Objekt anhand der Objekte aus, die ein
Beziehungspfad `path` von ihm aus erreicht. Jeder Schritt ist `Beziehung` oder
`Beziehung:Richtung`, mit der Richtung `forward` (Standard), `backward` oder
`either`. Die Schritte werden nacheinander durchlaufen und erreichen nie das
Objekt selbst. Beziehungsnamen sind die eigenen Namen der Quelle, etwa
IFC-Beziehungsentitäten, keine Konzepte; der verschachtelte `selector` nennt
Konzepte wie jeder andere Selektor und wird gegen dieselben Kataloge gebunden.

| `quantifier` | Wählt aus, wenn |
| --- | --- |
| `any` (Standard) | mindestens ein erreichtes Objekt passt |
| `all` | jedes erreichte Objekt passt und mindestens eines erreicht wird |
| `none` | kein erreichtes Objekt passt, auch wenn keines erreicht wird |

Normalisiertes JSON lässt den Standardwert `any` weg, und der verschachtelte
Selektor behält seine eigene Normalisierung. Der Binder lehnt einen leeren
`path`, einen Schritt mit Leerraum, einen leeren Namen oder eine andere Richtung
sowie jeden anderen Wert für `quantifier` ab.

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

## Ordner sind kosmetisch

`RuleFolder` dient Darstellung und Organisation. Seine Position ändert weder Selektorumfang, Regelidentität, Ausführungssemantik noch Vertrauen. Verbraucher können alternative Ansichten darstellen, ohne die Regeln umzuschreiben.

## Kompatibilitätsstatus

Die aktuelle Schemaversion ist `0.1.0` und noch nicht stabil. Die geplante Kompatibilitätspolitik steht in der [Roadmap](../community/roadmap.de.md), Vertragsänderungen im [Changelog](../community/changelog.de.md).
