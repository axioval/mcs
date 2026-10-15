# Wie Axioval zusammenpasst

Diese Seite öffnet die vier Ideen der Bilderreise und zeigt, was hinter jeder
Idee steckt. Das einfache Bild bleibt gleich: gemeinsame Begriffe, wiederverwendbare
Prüfrezepte, ausgefüllte Prüfungen und ein Paket, das alles zusammenhält.

Die genauen technischen Namen stehen jeweils dort, wo Werkzeugentwickler sie
brauchen. Alle anderen können der Erklärung ohne Quelltext folgen.

<div class="diagram-frame" markdown>

<picture class="responsive-diagram">
  <source media="(max-width: 44rem)" srcset="../../assets/images/building-blocks-mobile.svg">
  <img src="../../assets/images/building-blocks.svg" alt="Das Wörterbuch, Rezept, die ausgefüllte Karte und das Paket von Axioval">
</picture>

</div>

## 1. Vokabular

Ein Definitionspaket kann drei unabhängige Konzeptkataloge deklarieren:

| Konzept | Zweck | Beispiel |
| --- | --- | --- |
| `ObjectTypeDefinition` | Wiederverwendbarer Modellobjekttyp | IFC `IfcWall` |
| `PropertyDefinition` | Wiederverwendbare Eigenschaftsidentität und Wertart | boolesches `LoadBearing` |
| `PropertySetDefinition` | Optionaler externer Container-Qualifizierer | `Pset_WallCommon` |

Jedes Konzept hat eine stabile qualifizierte ID und kann verifizierte
`ExternalName`-Bindungen besitzen. Regeln referenzieren die stabile ID. Adapter
ordnen nur authentifizierte Bindungen unterstützten Modellschemata zu;
projektlokale Konzepte bleiben ausdrücklich lokal.

!!! important
    `PropertySetDefinition` führt Eigenschaften **nicht** auf und besitzt sie nicht. Eine Eigenschaft kann in mehreren externen Containern erscheinen. Die Containerzugehörigkeit wird erst normativ, wenn ein Selektor oder `PropertyReferenceValue` ein Set nennt.

## 2. Vorlage

Eine `RuleDefinition` deklariert:

- eine stabile Definitions-ID;
- eine stabile `capability`, die Anwendungen ausdrücklich implementieren; und
- typisierte Parameterdefinitionen.

??? example "Quelltext oder Befehle anzeigen"
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

`referencedValueKind` schließt eine subtile Typlücke: Diese boolesche Vorlage kann nicht an eine Zeichenketten-Eigenschaft gebunden werden.

Eine Vorlage kann außerdem einen Parameter mit `fixed = true` festlegen. Jede Instanz übernimmt dann seinen `defaultValue` und darf keinen eigenen angeben, sodass Pakete auf derselben Vorlage dasselbe prüfen. Wer einen festgelegten Parameter ändern will, forkt die Definition; siehe die [Schemareferenz](../reference/schema.de.md#ruledefinition).

## 3. Instanz

Eine `RuleInstance` bindet eine bekannte Definition an konkrete Werte. Ihre
Anwendbarkeit kann aus einem Selektor oder aus benannten Zielgruppen bestehen,
während Anforderungen festhalten, was für diese Gruppen gelten muss. Optionale
erklärende Bilder erleichtern das Verständnis, beeinflussen aber niemals die
Ausführung. Instanzen sind Politik, die ABox-ähnliche Ebene, und gehören in
externe Regelwerk-Repositories. Dieses Schema-Repository enthält sie nur unter
`examples/`.

## 4. Paket und Normalisierung

`axioval.json` identifiziert das Paket und jeden Definitions-Einstiegspunkt statisch. Erst nachdem alle Einstiegspunkte im Repository bleiben und jedes Kandidaten-JSON semantisch gebunden wurde, wird die Ausgabe zum normalisierten Austauschformat.

<div class="diagram-frame" markdown>

![Ein Paket wird untersucht, sicher geöffnet, vollständig geprüft und an ein kompatibles Werkzeug übergeben](../assets/images/trust-path.de.svg)

</div>

## Wofür Axioval zuständig ist

<ul class="scope-list scope-list--included">
  <li>Gemeinsame, stabile Begriffe für Fakten am Gebäude</li>
  <li>Typisierte, wiederverwendbare Beschreibungen von Prüfungen</li>
  <li>Ausgefüllte Prüfungen, die als Daten geteilt werden können</li>
  <li>Ein Paketvertrag, der unvollständige oder widersprüchliche Eingaben ablehnt</li>
</ul>

## Wofür Axioval bewusst nicht zuständig ist

<ul class="scope-list scope-list--excluded">
  <li>Modelldateien öffnen oder IFC-Beziehungen durchlaufen</li>
  <li>Geometrie berechnen</li>
  <li>Ausführbare Regellogik eines Pakets ausführen</li>
  <li>Das kanonische Laufzeit-IR einer Anwendung festlegen</li>
  <li>Registry-Vertrauen aus Repository-Eigentum ableiten</li>
</ul>
