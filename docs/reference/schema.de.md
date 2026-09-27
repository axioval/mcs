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
| `Selectors.pkl` | Selektoren für Objekttyp, Eigenschaft, Klassifikation und boolesche Zusammensetzung |
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

## Selektoren

Selektoren sind deklarativ und werden rekursiv validiert:

- `all`
- `entityType` mit einer kanonischen Objekttyp-ID
- `property` mit kanonischer Eigenschafts-ID und optionalem Set-Qualifizierer
- `classification`
- `allOf`, `anyOf` und `not`

Ein Vergleichswert auf einem Eigenschaftsselektor muss zur katalogisierten `valueKind` der referenzierten Eigenschaft passen. `exists` lehnt einen Vergleichswert ab. Jeder andere Operator benötigt einen.

| Operator | Wert | Bedeutung |
| --- | --- | --- |
| `equals`, `notEquals` | Art der Eigenschaft | gleich oder ungleich |
| `lessThan`, `lessThanOrEquals`, `greaterThan`, `greaterThanOrEquals` | `integer`, `number`, `quantity` oder `string` | geordneter Vergleich |
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
