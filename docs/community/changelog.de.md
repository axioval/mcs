---
hide:
  - edit
---

# Änderungsprotokoll

Alle wichtigen Änderungen an Axioval MCS werden hier dokumentiert.

Das Format folgt [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Paket- und Schemakompatibilität folgt nach einem Release [Semantic Versioning](https://semver.org/). Der aktuelle Vertrag `0.1.0` ist noch nicht stabil.

## [Unveröffentlicht]

### Hinzugefügt

- Ausdrücke und abgeleitete Werte wie in der prüfenden Anwendung: `Expressions.pkl` typisiert jede Art von Ausdrucksknoten, Parameter mit `kind: expression`, den Selektor `expression` und die abgeleiteten Werte `values` eines Regelsatzes. Normalisiertes JSON folgt bytegenau der Ausgabe der prüfenden Anwendung; der Binder lehnt unbekannte Arten und Felder, zu tiefe oder zu große Ausdrücke, unbekannte Konzepte und Werte, unzulässige Parameter- und Regelergebniszugriffe sowie Zyklen ab. Die goldenen Ausdrucksfixtures liegen in `tests/fixtures/expression`, das Beispiel `examples/expressions` leitet die Neigung einer Rampe ab.
- Dokumentationsseite mit MkDocs Material und GitHub-Pages-Bereitstellung.
- Wiederverwendbare Vokabularkomponenten `ObjectTypeDefinition`, `PropertyDefinition` und unabhängige `PropertySetDefinition`.
- Kanonische Varianten `ObjectTypeReferenceValue` und `PropertyReferenceValue`.
- Optionale genaue Property-Set-Qualifizierung ohne Eigentum von Eigenschaften.
- `referencedValueKind`-Beschränkungen für typisierte Eigenschaftsreferenz-Parameter.
- Vollständiges Lernbeispiel DIN 276 KG 331 für Objekttyp sowie strenge `LoadBearing`- und containerunabhängige `IsExternal`-Anforderungen.
- Negative Tests für unbekannte Konzepte und nicht passende Eigenschaftsarten.
- Leitfaden für Mitwirkende, Roadmap, AGPL-Lizenz und GitHub-Sponsors-Konfiguration.
- Barrierefreie lokale SVG-Diagramme mit getrennten breiten und mobilen Kompositionen.
- Eine Build-Prüfung für Prosa, die Halbgeviert- und Geviertstriche in Repository-Markdown ablehnt.

### Geändert

- Selektoren für Entitätstypen referenzieren nun wiederverwendbare Objekttypkonzepte, statt rohe externe Typ-System-/Namenspaare zu wiederholen.
- Das minimale Eigenschaftsbeispiel verwendet eine kanonische Eigenschaftsreferenz statt `propertySet` und `property` als gleichrangige Zeichenkettenparameter zu behandeln.
- Die normalisierte Ausgabe eines Definitionspakets enthält nun Objekt-, Eigenschafts- und Property-Set-Kataloge.
- IFC-Entitätsbindungen verwenden nun die semantische HTTPS-Typsystemidentität der jeweiligen Version aus `openbim.ifc@0.2.0`; Eigenschafts- und Set-Beispiele bleiben im Projekteigennamensraum, bis paket-eigene PSD/QTO-Vorkommen veröffentlicht sind.
- Die öffentliche Seite beginnt nun mit einer dreiseitigen Bilderreise in einfacher Sprache und hält Referenzmaterial für Werkzeugentwickler getrennt.
- Tutorial-Quelltext und Validierungsbefehle sind standardmäßig eingeklappt, bleiben aber statisch hervorgehoben und bei Bedarf verfügbar.

### Behoben

- Apple-Pkl-Codeblöcke verwenden nun einen dedizierten serverseitigen Lexer, einschließlich benutzerdefinierter Zeichenkettenbegrenzer beliebiger Länge, und der Dokumentationsbuild schlägt fehl, wenn sie wieder als unformatierter Text erscheinen.
- Die Validierung von Definitionsvorgaben überschattet beim Binden nicht mehr das aktive Regelwerkdokument.

### Sicherheit

- Die sandboxgeschützte Pkl-Auswertung erlaubt prüfsummengebundene Paketmodule und deren erforderliche, auf Paket-Hosts begrenzte HTTPS-Metadaten und Release-Assets. Beliebige HTTPS-, Datei- und Umgebungsressourcen sowie Zugriffe außerhalb des Repository-Stammverzeichnisses bleiben gesperrt. Die Prüfung löst ein kopiertes Projekt mit leerem Cache auf und verlangt, dass die erzeugte Abhängigkeitssperre bytegenau den eingecheckten Daten entspricht.
- Die Normalisierung lehnt unbekannte Objekt-, Eigenschafts- und Property-Set-IDs, nicht passende referenzierte Eigenschaftsarten und nicht aufgelöste strenge Container-Qualifizierer ab.

## [0.1.0] - 2026-08-31

### Hinzugefügt

- Erste Pkl-Autorenmodule für Typen, Werte, Selektoren, Definitionen und Regelwerke.
- Statischer `axioval.json`-Registry-Manifestvertrag.
- Auf das Repository begrenzte Pkl-Auswertung und deterministische normalisierte Snapshots.
- Fail-closed Binder für paket-, definitions-, selektor- und parameterübergreifende Dokumente.
- Minimales Nicht-Produktionspaket und CI-Validierungsablauf.

[Unveröffentlicht]: https://github.com/axioval/mcs/compare/49a2d765fe9a6a5b2f9cbf650500c30b9d6068d3...HEAD
[0.1.0]: https://github.com/axioval/mcs/commit/49a2d765fe9a6a5b2f9cbf650500c30b9d6068d3
