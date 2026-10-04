# Ein Paket erstellen

Ein Paket hält Begriffe, Prüfungen und Versionsangaben zusammen. So kann ein
anderes Team alles prüfen und verwenden. Folgen Sie den sieben Schritten in
dieser Reihenfolge. Quelltext müssen Sie nur öffnen, wenn Sie die technischen
Einzelheiten sehen möchten.

!!! tip "Neu bei Axioval?"
    Lesen Sie vor dem Einstieg die [vier Bausteine](guide/building-blocks.de.md) und das [Wandbeispiel](tutorials/din-276-331.de.md).

## 1. Die Paketgrenze anlegen

??? example "Quelltext oder Befehle anzeigen"
    ```text
    my-rules/
    ├── axioval.json
    ├── PklProject
    ├── definitions.pkl
    ├── ruleset.pkl
    └── expected/
        ├── definitions.json
        └── ruleset.json
    ```

Legen Sie die unterstützte Pkl-Version fest und halten Sie jedes vom Manifest ausgewählte Modul innerhalb der Repository-Wurzel.

## 2. Stabile IDs wählen

Verwenden Sie qualifizierte IDs für die Identität von Paket, Vokabular, Vorlage und Fähigkeit. Kodieren Sie keine veränderlichen Bezeichnungen oder Ordnerpfade in IDs.

??? example "Quelltext oder Befehle anzeigen"
    ```text
    https://example.org/axioval/property/fire-rating
    https://example.org/axioval/rule/property-exists
    ```

Lokale Ordner- und Regel-IDs verwenden die kleinere, repository-lokale Bezeichnersyntax.

## 3. Vokabular vor Politik definieren

Deklarieren Sie wiederverwendbare Objekttypen, Eigenschaften und Property-Set-Qualifizierer in einem Modul, das `schema/Definitions.pkl` ergänzt. Eigenschaften und Sets sind unabhängige Kataloge. Erstellen Sie keine verpflichtende Hierarchie.

## 4. Eine Fähigkeitsvorlage wiederverwenden oder definieren

Eine `RuleDefinition` ist nur gültig, wenn prüfende Anwendungen ihre Fähigkeit kennen. Eine neue Fähigkeits-ID zu einem Paket hinzuzufügen, lässt Anwendungen sie nicht ausführen. Stimmen Sie portable Fähigkeitssemantik getrennt ab und schlagen Sie fehlgeschlossen fehl, wenn eine Anwendung sie nicht unterstützt.

## 5. Instanzen erstellen

Ein Regelwerkmodul ergänzt `schema/RuleSets.pkl`, deklariert jedes Definitionspaket und erstellt typisierte Instanzen. Die Anwendbarkeit wählt die zu prüfenden Objekte. Legen Sie das erwartete Ergebnis nicht in die Anwendbarkeit, wenn dadurch Verstöße verborgen würden.

!!! example "Umfang im Vergleich zur Behauptung"
    Um zu verlangen, dass jedes `DIN 276 / 331`-Objekt eine `IfcWall` ist, wählen Sie über die Klassifikation aus und behaupten den Objekttyp in der Regel. Nur Wände auszuwählen würde falsch typisierte Objekte still ausschließen.

Ist eine Anforderung eine Rechnung, etwa eine Neigung aus Steigungshöhe und Lauflänge, beschreiben Sie sie als Ausdruck und benennen gemeinsame Zwischenwerte einmal in `values` des Regelsatzes; siehe [Mit Ausdrücken rechnen](expressions.de.md).

## 6. Das statische Manifest deklarieren

??? example "Quelltext oder Befehle anzeigen"
    ```json
    {
      "$schema": "schema/registry-manifest.schema.json",
      "manifestVersion": "0.1.0",
      "kind": "ruleset",
      "id": "https://example.org/axioval/my-rules",
      "version": "0.1.0",
      "schemaVersion": "0.1.0",
      "entrypoint": "ruleset.pkl",
      "definitionEntrypoints": ["definitions.pkl"]
    }
    ```

Registry-Implementierungen untersuchen diese Datei vollständig, bevor sie Pkl aufrufen. Absolute Pfade, Traversal, Nicht-Pkl-Einstiegspunkte, unbekannte Felder und fehlende Definitionsmodule werden abgelehnt.

## 7. Validieren und versionieren

Führen Sie lokal und in CI dieselbe Sperre aus:

??? example "Quelltext oder Befehle anzeigen"
    ```bash
    PATH="$HOME/.local/bin:$PATH" ./scripts/check.sh
    ```

Committen Sie Pkl-Quelltext, Manifest und deterministische normalisierte Snapshots zusammen. Verwenden Sie semantische Paketversionen und erläutern Sie Kompatibilitätsänderungen in einem Changelog.

## Checkliste für die Veröffentlichung

- [ ] keine Geheimnisse oder host-spezifischen absoluten Pfade;
- [ ] ausdrückliche Paketlizenz und Herkunft;
- [ ] alle Fähigkeiten dokumentiert und von Zielanwendungen unterstützt;
- [ ] strenge Property-Set-Qualifizierer nur bei beabsichtigter Semantik;
- [ ] negative Tests beweisen, dass fehlerhafte Referenzen und falsche Wertarten fehlschlagen;
- [ ] normalisierte Snapshots aus dem committeten Quelltext erzeugt;
- [ ] Registry-Einreichung verweist auf eine unveränderliche Revision oder ein Release.
