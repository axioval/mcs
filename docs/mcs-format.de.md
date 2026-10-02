# MCS-Containerformat

MCS Version 0.1.0 ist der deterministische Transportcontainer für ein
Axioval-Regelwerk. Er enthält überprüfbaren Pkl-Quelltext für Autoren und das
deklarative normalisierte JSON, das Anwendungen zur Modellprüfung verwenden. Er
ist kein Format für ausführbare Plugins.

## Befehle

??? example "MCS-Befehle anzeigen"
    ```bash
    python3 scripts/mcs.py pack examples/minimal /tmp/minimal.mcs --repository-root .
    python3 scripts/mcs.py inspect /tmp/minimal.mcs
    python3 scripts/mcs.py verify /tmp/minimal.mcs
    ```

`pack` lehnt Ausgaben ohne Endung `.mcs` und vorhandene Dateien ohne `--force`
ab. `inspect` liest und prüft nur Metadaten und Inventar strukturell. `verify`
ist eine Zertifizierung: Der Befehl materialisiert geprüfte Dateien sicher,
wertet Pkl in der vorhandenen Sandbox aus, vergleicht normalisiertes JSON Byte
für Byte und bindet Definitionen sowie Regelwerk mit ihren Paketressourcen.

## Bytevertrag

Eine MCS-Datei ist ein ZIP-Archiv ohne Archivkommentar. Ihr erstes lokales
Element heißt genau `mimetype`, ist gespeichert statt komprimiert und enthält
genau die ASCII-Bytes `application/vnd.axioval.mcs+zip`. Es gibt **keinen
Zeilenumbruch am Ende**. Das zweite Element ist `META-INF/mcs.json`. Schreiber
verwenden festen Zeitstempel, Berechtigungen, Plattform, Flags,
Komprimierungsstufe, kanonisches JSON und sortierte übrige Namen. Derselbe
Repositoryzustand erzeugt daher zweimal dieselben Bytes.

Metadaten deklarieren `sourceRoot`, `packageRoot`, Manifestpfad, festgelegte
Pkl-Version, Paketidentität, Zuordnung normalisierter Quellmodule und ein
SHA-256/Größe/Rolle-Inventar für jede Nutzlast. Die Topologie bleibt relativ zum
Repository unter `source/`; Importe werden nicht umgeschrieben. Standardmodule
`pkl:` werden nicht archiviert.

## Annahmegrenze

Leser lehnen fehlerhafte oder mehrdeutige ZIP-Strukturen ab, bevor sie Dateien
schreiben: unsichere Namen, Duplikate und Unicode- oder Groß-/Kleinschreibungs-
Kollisionen, Links oder Spezialmodi, nicht unterstützte Komprimierung,
Verschlüsselung, Datenbeschreibungen, zu große oder stark komprimierte Elemente,
unbekannte Nutzlasten und fehlerhafte Metadaten schlagen geschlossen fehl.
Dateien werden direkt in ein begrenztes temporäres Verzeichnis geschrieben,
niemals mit ZIP-Extraktionshilfen. Version 0.1.0 erlaubt höchstens 512 Elemente,
10.000.000 Byte pro Element, je 64 MiB komprimierte und unkomprimierte
Gesamtnutzlast, 256 KiB Metadaten und ein Entpackverhältnis von 100:1 pro Element.
`mimetype` verwendet `ZIP_STORED`; alle anderen Elemente verwenden DEFLATE der
Stufe 9.

Beim Packen werden Manifest, Root-`PklProject`, `.pkl-version` und bei
Paketabhängigkeiten die verpflichtende `PklProject.deps.json`, mindestens eine
direkte Root-`LICENSE*`-Datei und die genaue
lokale Pkl-Abhängigkeit über `import`/`amends`/`extends`, relatives Manifestschema,
deklarierte Assets (erklärende Bilder und die Tabellendateien von Regelsatz und
Definitionen) und direkte `README*`/`LICENSE*`/`NOTICE*`-Dateien des Pakets
aufgenommen. Abhängigkeitsdirektiven müssen genau ein gewöhnliches Zeichenketten-
Literal in einer Zeile verwenden. Dynamische, globbasierte, benutzerdefinierte,
externe, entweichende oder verlinkte Abhängigkeiten sowie alle Pkl-Ressourcen-
Leseaufrufe (`read`, `read?`, `read*` und `readGlob`) werden abgelehnt. Ein
passendes normalisiertes Ergebnis kann Quellauswertung, Prüfung des exakten
Abschlusses und Bindung nicht umgehen.

Ein Paketimport bleibt nur dann extern, wenn sein `@alias` im `PklProject`
deklariert ist und die Sperrdatei dessen exakte `package:`-URI an einen
prüfsummengebundenen `projectpackage:`-Eintrag bindet. Beim Packen wird das
kopierte Projekt mit leerem Cache aufgelöst. Fehlende, veraltete oder remote
ungültige Prüfsummen werden abgelehnt. Die vollständige Prüfung wertet die Quelle
erneut aus und darf auf prüfsummengebundene Paketmetadaten und Release-Assets
zugreifen, weil Pkl Paketressourcen beim Import validiert. Zusätzlich bestätigt
sie die strukturelle Bindung und die exakt inventarisierten Bytes. Nur `inspect`
ist eine reine Offline-Strukturprüfung und behauptet keine erneute Remote-
Authentifizierung.
