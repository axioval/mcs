from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.parsers import expat

QUALIFIED_ID = re.compile(r"^[a-z][a-z0-9+.-]*:.+$")
IDENTIFIER = re.compile(r"^[a-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)*$")
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
VALUE_KINDS = {
    "string",
    "boolean",
    "integer",
    "number",
    "quantity",
    "enum",
    "reference",
    "objectTypeReference",
    "propertyReference",
    "selector",
    "stringList",
    "referenceList",
    "table",
    "date",
    "dateTime",
}
VALUE_KEYS = {kind: {"type", "value"} for kind in VALUE_KINDS}
VALUE_KEYS["quantity"] = {"type", "value", "unit"}
VALUE_KEYS["objectTypeReference"] = {"type", "objectType", "includeSubtypes"}
VALUE_KEYS["propertyReference"] = {"type", "property"}
PROPERTY_VALUE_KINDS = VALUE_KINDS - {
    "objectTypeReference",
    "propertyReference",
    "selector",
    "table",
}
# Table column kinds and the value variant each cell is written as.
COLUMN_VALUE_KINDS = {
    "string": "string",
    "textPattern": "string",
    "number": "number",
    "quantity": "quantity",
    "integer": "integer",
    "boolean": "boolean",
    "selector": "selector",
    "reference": "reference",
    "date": "date",
    "dateTime": "dateTime",
}
# The value variant naming a data file in the package whose rows fill a
# `table` parameter, and its keys.
TABLE_FILE = "tableFile"
TABLE_FILE_KEYS = {"type", "path", "sha256", "columns"}
# A table file's lowercase hex SHA-256.
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
# The largest table file, and the largest workbook member, the engine reads.
TABLE_FILE_LIMIT_BYTES = 10_000_000
# A whole number as the engine parses a 64-bit integer cell.
INTEGER_LITERAL = re.compile(r"[+-]?[0-9]+")
# The columns of a relation's listed pairs: the text naming each end.
RELATION_PAIR_COLUMNS = [
    {"id": "from", "kind": "string", "required": True},
    {"id": "to", "kind": "string", "required": True},
]
# How a relation pairs its objects.
RELATION_KINDS = {"property", "pairs", "supplied"}
SELECTOR_OPERATORS = {
    "equals",
    "notEquals",
    "lessThan",
    "lessThanOrEquals",
    "greaterThan",
    "greaterThanOrEquals",
    "matches",
    "like",
    "contains",
    "oneOf",
    "noneOf",
    "exists",
    "isEmpty",
    "isNotEmpty",
}
# Operators judging presence rather than comparing a value: they take no
# value, no quantifier, and no text option.
PRESENCE_OPERATORS = {"exists", "isEmpty", "isNotEmpty"}
ORDERING_OPERATORS = {
    "lessThan",
    "lessThanOrEquals",
    "greaterThan",
    "greaterThanOrEquals",
}
ORDERED_VALUE_KINDS = {"integer", "number", "quantity", "string", "date", "dateTime"}
# Calendar value kinds, which alone take a selector `precision`.
TEMPORAL_VALUE_KINDS = {"date", "dateTime"}
TEMPORAL_PRECISIONS = {"day"}
TEXT_PATTERN_OPERATORS = {"matches", "like", "contains"}
LIST_OPERATORS = {"oneOf", "noneOf"}
# Value kinds compared as text, so case folding and trimming apply.
TEXT_VALUE_KINDS = {"string", "enum", "reference"}
QUANTIFIERS = {"any", "all"}
# List-valued property kinds and the kind of each element a quantified
# comparison tests.
LIST_ELEMENT_KINDS = {"stringList": "string", "referenceList": "reference"}
RELATED_QUANTIFIERS = {"any", "all", "none"}
# The source metadata fields a source selector compares.
SOURCE_FIELDS = {"fileName", "application", "schema", "project", "timestamp"}
# The directions a relationship path step may state.
PATH_DIRECTIONS = ("forward", "backward", "either")
# A source relationship name in a related-selector or category path step.
RELATED_PATH_RELATIONSHIP = re.compile(r"[^:\s|]+")
# A source relationship name in a `bottom_above_level` path step, which the
# measured name's own `;` and the path's `,` separate.
MEASURED_PATH_RELATIONSHIP = re.compile(r"[^:\s|,;]+")
# A derived relationship the checking engine computes, with its optional
# tolerances, as a path step may name it.
DERIVED_RELATIONSHIP = re.compile(
    r"axioval:derived\.(?!(?:group|relation)(?![a-z0-9-]))[a-z][a-z0-9-]*"
    r"(;[a-z]+=[0-9]+(\.[0-9]+)?)*"
)
# A ruleset grouping's ID: not blank, and free of `:`, `;`, `|`, `/` and
# whitespace, since it is part of the identity of every group it derives.
GROUPING_ID = re.compile(r"[^:;|/\s]+")
# The derived relationship from each member of a grouping to its group,
# `axioval:derived.group;by=<grouping>`; `backward` reaches the members.
DERIVED_GROUP_RELATIONSHIP = re.compile(r"axioval:derived\.group;by=([^:;|/\s]+)")
# A ruleset relation's ID, free of the same characters as a grouping's, since
# it is part of the identity of every pair it relates.
RELATION_ID = GROUPING_ID
# The relationship a relation the same ruleset declares runs along,
# `axioval:derived.relation;id=<relation>`; `backward` runs from a to-object
# to its from-objects.
DERIVED_RELATION_RELATIONSHIP = re.compile(
    r"axioval:derived\.relation;id=([^:;|/\s]+)"
)
# Every path step alternative naming a declared relation contains this.
RELATION_RELATIONSHIP_PREFIX = "axioval:derived.relation;id="
# A relationship kind every source answers under its own relationship types,
# as the engine names them (`axioval:relationship.<kind>`).
RELATIONSHIP_KIND = re.compile(
    r"axioval:relationship\.(containment|aggregation|voids|fills|space-boundary"
    r"|type|group|connection)"
)
PATH_STEP_GRAMMAR = (
    "'Relationship[|Relationship...][:forward|backward|either][+]', each "
    "relationship a source relationship name, a derived relationship "
    "'axioval:derived.<name>', a grouping's "
    "'axioval:derived.group;by=<grouping>', a relation's "
    "'axioval:derived.relation;id=<relation>' or a relationship kind "
    "'axioval:relationship.<kind>'"
)
# Reserved property sets: engine vocabulary that binds to itself, never a
# package concept.
RESERVED_PROPERTY_SETS = {
    "axioval:attributes",
    "axioval:type-attributes",
    "axioval:presentation",
    "axioval:material",
    "axioval:body",
    "axioval:classification",
    "axioval:measured",
    "axioval:group",
}
# The reserved set naming the classes a ruleset's classifications derive: its
# property names are classification IDs of the same ruleset.
CLASSIFICATION_SET = "axioval:classification"
# Reserved sets the engine derives rather than a source states: their property
# names are engine or ruleset vocabulary and bind to no concept.
# The reserved set of values measured from geometry, its names without
# parameters, and its names taking `;key=value` parameters, matched ignoring
# ASCII case.
MEASURED_SET = "axioval:measured"
MEASURED_NAMES = {
    "extent_x",
    "extent_y",
    "extent_z",
    "bottom",
    "top",
    "area",
    "volume",
    "x",
    "y",
    "z",
    "level_height",
}
MEASURED_BOTTOM_ABOVE_LEVEL = "bottom_above_level"
MEASURED_BOUNDARY_AREA = "boundary_area"
# A decimal number as the engine parses one.
DECIMAL = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")
# The whitespace the engine trims around names, keys, and values.
TRIMMED = (
    "\t\n\x0b\x0c\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)
# The reserved set stating what the engine knows of a derived group: the
# value its members share as text (`key`) and how many they are (`members`).
# No other object has either.
GROUP_SET = "axioval:group"
GROUP_NAMES = {"key": "string", "members": "integer"}
# How a grouping groups its members.
GROUPING_KINDS = {"property", "classification", "compartment"}
DERIVED_PROPERTY_SETS = {CLASSIFICATION_SET, MEASURED_SET, GROUP_SET}
CLASSIFICATION_MODES = {"firstMatch", "allMatch"}
SEVERITIES = {"info", "warning", "error"}
# How another rule judged an object, as a rule-outcome selector selects it.
RULE_OUTCOMES = {"passed", "failed"}
# When a gated rule runs, and on what.
GATE_CONDITIONS = {"allIfPassed", "allIfFailed", "passedObjects", "failedObjects"}
# A discipline name a source declares; no vocabulary is fixed.
DISCIPLINE_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
# The Unicode general categories an XML Schema `\p{...}` escape may name.
XSD_CATEGORIES = {
    *"LMNPZSC",
    *("Lu", "Ll", "Lt", "Lm", "Lo", "Mn", "Mc", "Me", "Nd", "Nl", "No"),
    *("Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po", "Zs", "Zl", "Zp"),
    *("Sm", "Sc", "Sk", "So", "Cc", "Cf", "Co", "Cn"),
}
# Characters an XML Schema single-character escape may follow `\` with.
XSD_SINGLE_ESCAPES = set("nrt\\|.-^?*+{}()[]")
# Multi-character escapes; their Python spelling compiles alike.
XSD_CLASS_ESCAPES = set("sSwWdD")
XSD_QUANTITY = re.compile(r"\{[0-9]+(,[0-9]*)?\}")
IMAGE_MEDIA_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
SOURCE_KINDS = {
    "standard",
    "regulation",
    "technicalSpecification",
    "contract",
    "projectPolicy",
    "guidance",
    "other",
}
LOCATOR_KINDS = {
    "part",
    "chapter",
    "section",
    "clause",
    "paragraph",
    "annex",
    "table",
    "figure",
    "page",
    "item",
    "other",
}
PUBLICATION_DATE = re.compile(r"^[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?$")
# ISO 8601 extended date and date-time literals, as XML Schema writes
# `xs:date` and `xs:dateTime`. The shape is checked here; the calendar, the
# time of day, and the offset range are checked by `temporal_literal_error`.
DATE_LITERAL = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})(Z|[+-][0-9]{2}:[0-9]{2})?")
DATE_TIME_LITERAL = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def fail(context: str, message: str) -> None:
    raise SystemExit(f"validation failed: {context}: {message}")


def object_value(value: Any, context: str) -> dict[str, Any]:
    if type(value) is not dict:
        fail(context, "expected object")
    return value


def list_value(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        fail(context, "expected list")
    return value


def exact_keys(
    value: dict[str, Any], required: set[str], optional: set[str], context: str
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing or unknown:
        fail(context, f"missing={sorted(missing)}, unknown={sorted(unknown)}")


def localized_text(value: Any, context: str) -> None:
    value = object_value(value, context)
    exact_keys(value, {"default", "translations"}, set(), context)
    if type(value["default"]) is not str or not value["default"]:
        fail(context, "default text must be non-empty")
    translations = object_value(value["translations"], f"{context}.translations")
    if any(
        type(key) is not str or type(text) is not str
        for key, text in translations.items()
    ):
        fail(context, "translations must map locale tags to strings")


def string_list(value: Any, context: str) -> list[str]:
    values = list_value(value, context)
    if any(type(item) is not str for item in values):
        fail(context, "expected strings")
    return values


def package_metadata(value: Any, context: str) -> str:
    value = object_value(value, context)
    exact_keys(
        value,
        {"id", "name", "version", "authors"},
        {"description", "repository", "license"},
        context,
    )
    if type(value["id"]) is not str or not QUALIFIED_ID.fullmatch(value["id"]):
        fail(context, "invalid package id")
    localized_text(value["name"], f"{context}.name")
    if type(value["version"]) is not str or not SEMVER.fullmatch(value["version"]):
        fail(context, "invalid package version")
    authors = string_list(value["authors"], f"{context}.authors")
    if any(not author for author in authors):
        fail(context, "authors must be non-empty strings")
    if "description" in value:
        localized_text(value["description"], f"{context}.description")
    for field in ("repository", "license"):
        if field in value and (type(value[field]) is not str or not value[field]):
            fail(context, f"{field} must be a non-empty string")
    return value["id"]


def validate_publication_date(value: Any, context: str) -> None:
    if type(value) is not str or not PUBLICATION_DATE.fullmatch(value):
        fail(context, "publicationDate must be ISO YYYY, YYYY-MM, or YYYY-MM-DD")
    parts = [int(part) for part in value.split("-")]
    try:
        if len(parts) == 1:
            date(parts[0], 1, 1)
        elif len(parts) == 2:
            date(parts[0], parts[1], 1)
        elif len(parts) == 3:
            date(*parts)
    except ValueError:
        fail(context, "publicationDate is not a valid calendar date")


def validate_https_url(value: Any, context: str) -> None:
    if type(value) is not str or any(
        character.isspace() or character == "\\" or ord(character) < 32
        for character in value
    ):
        fail(
            context,
            "URL must not contain whitespace, control characters, or backslashes",
        )
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError:
        fail(context, "URL host or port is malformed")
    if (
        parsed.scheme != "https"
        or hostname is None
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        fail(context, "URL must be absolute HTTPS without credentials")


def validate_sources(value: Any, context: str) -> dict[str, dict[str, Any]]:
    sources = object_value(value, context)
    for key, candidate in sources.items():
        source_context = f"{context}[{key!r}]"
        source = object_value(candidate, source_context)
        exact_keys(
            source,
            {"id", "kind", "designation", "title"},
            {"publisher", "edition", "publicationDate", "url"},
            source_context,
        )
        if (
            type(key) is not str
            or key != source["id"]
            or not QUALIFIED_ID.fullmatch(key)
        ):
            fail(source_context, "source map key must equal its qualified id")
        if type(source["kind"]) is not str or source["kind"] not in SOURCE_KINDS:
            fail(source_context, "unknown source kind")
        localized_text(source["title"], f"{source_context}.title")
        for field in ("designation", "publisher", "edition"):
            if field in source and (
                type(source[field]) is not str or not source[field]
            ):
                fail(source_context, f"{field} must be a non-empty string")
        if "publicationDate" in source:
            validate_publication_date(
                source["publicationDate"], f"{source_context}.publicationDate"
            )
        if "url" in source:
            validate_https_url(source["url"], f"{source_context}.url")
    return sources


def validate_citations(
    value: Any,
    sources: dict[str, dict[str, Any]],
    context: str,
    seen_ids: set[str] | None = None,
) -> set[str]:
    seen = seen_ids if seen_ids is not None else set()
    for index, candidate in enumerate(list_value(value, context)):
        citation_context = f"{context}[{index}]"
        citation = object_value(candidate, citation_context)
        exact_keys(citation, {"id", "sourceId", "locators"}, {"note"}, citation_context)
        citation_id = citation["id"]
        source_id = citation["sourceId"]
        if type(citation_id) is not str or not IDENTIFIER.fullmatch(citation_id):
            fail(citation_context, "invalid citation id")
        if citation_id in seen:
            fail(citation_context, f"duplicate citation id {citation_id!r}")
        seen.add(citation_id)
        if type(source_id) is not str or source_id not in sources:
            fail(citation_context, f"unknown sourceId {source_id!r}")
        if "note" in citation:
            localized_text(citation["note"], f"{citation_context}.note")
        locators: set[tuple[str, str]] = set()
        for locator_index, candidate_locator in enumerate(
            list_value(citation["locators"], f"{citation_context}.locators")
        ):
            locator_context = f"{citation_context}.locators[{locator_index}]"
            locator = object_value(candidate_locator, locator_context)
            exact_keys(locator, {"kind", "value"}, set(), locator_context)
            kind = locator["kind"]
            locator_value = locator["value"]
            if type(kind) is not str or kind not in LOCATOR_KINDS:
                fail(locator_context, "unknown locator kind")
            if type(locator_value) is not str or not locator_value:
                fail(locator_context, "locator value must be non-empty")
            locator_key = (kind, locator_value)
            if locator_key in locators:
                fail(locator_context, "duplicate locator")
            locators.add(locator_key)
    return seen


def well_formed_pattern(pattern: str) -> bool:
    """Whether every backslash in a wildcard pattern escapes a character."""
    escaped = False
    for character in pattern:
        escaped = not escaped and character == "\\"
    return not escaped


def xsd_pattern_error(pattern: str) -> str | None:
    """Why `pattern` is not an XML Schema regular expression matched exactly.

    Mirrors the checking engine's translation: `^` and `$` are ordinary
    characters, and character-class subtraction, the `\\i` and `\\c` name
    escapes, and `\\p{Is...}` block escapes are refused rather than
    approximated. The translated pattern is compiled to catch syntax errors.
    """
    out: list[str] = []
    index = 0
    in_class = False
    class_start = 0
    previous_class_char: str | None = None
    # Whether the previous atom already carries a quantifier.
    quantified = False

    def escape(position: int) -> tuple[str, int]:
        if position >= len(pattern):
            raise ValueError("pattern ends with a backslash")
        escaped = pattern[position]
        if escaped in XSD_CLASS_ESCAPES or escaped in XSD_SINGLE_ESCAPES:
            return "\\" + escaped, position + 1
        if escaped in "pP":
            if pattern[position + 1 : position + 2] != "{":
                raise ValueError(f"'\\{escaped}' needs a braced name")
            end = pattern.find("}", position + 2)
            if end < 0:
                raise ValueError("unterminated '\\p{'")
            name = pattern[position + 2 : end]
            if name.startswith("Is"):
                raise ValueError(f"block escape '\\p{{{name}}}' is not supported")
            if name not in XSD_CATEGORIES:
                raise ValueError(f"{name!r} is not a Unicode category")
            # Python has no category escapes; any one character compiles alike.
            return "a", end + 1
        if escaped in "iIcC":
            raise ValueError(f"name escape '\\{escaped}' is not supported")
        raise ValueError(f"'\\{escaped}' is not an XML Schema escape")

    def follows_atom() -> bool:
        return not quantified and bool(out) and out[-1] not in ("(", "|")

    try:
        while index < len(pattern):
            character = pattern[index]
            if in_class:
                if character == "]":
                    if index == class_start:
                        raise ValueError("empty character class")
                    in_class = False
                    out.append("]")
                    index += 1
                elif character == "\\":
                    translated, index = escape(index + 1)
                    out.append(translated)
                elif character == "-" and pattern[index + 1 : index + 2] == "[":
                    raise ValueError("character-class subtraction is not supported")
                elif character == "-" and previous_class_char == "-":
                    raise ValueError(
                        "'--' in a character class is not XML Schema syntax"
                    )
                elif character == "[":
                    raise ValueError("an unescaped '[' inside a character class")
                else:
                    # Set operators in Python classes; literals in XML Schema.
                    out.append("\\" + character if character in "&~|" else character)
                    index += 1
                previous_class_char = character
                continue
            if character in "*+?":
                if not follows_atom():
                    raise ValueError(f"{character!r} does not follow an atom")
                out.append(character)
                quantified = True
                index += 1
                continue
            if character == "{":
                quantity = XSD_QUANTITY.match(pattern, index)
                if quantity is None:
                    raise ValueError("an unescaped '{' that is not a quantity")
                if not follows_atom():
                    raise ValueError("a quantity does not follow an atom")
                out.append(quantity.group())
                quantified = True
                index = quantity.end()
                continue
            quantified = False
            if character == "}":
                raise ValueError("an unescaped '}'")
            if character in "^$":
                out.append("\\" + character)
                index += 1
            elif character == "[":
                in_class = True
                previous_class_char = None
                out.append("[")
                index += 1
                if pattern[index : index + 1] == "^":
                    out.append("^")
                    index += 1
                class_start = index
            elif character == "(" and pattern[index + 1 : index + 2] == "?":
                raise ValueError("'(?' is not XML Schema syntax")
            elif character == "\\":
                translated, index = escape(index + 1)
                out.append(translated)
            else:
                out.append(character)
                index += 1
        if in_class:
            raise ValueError("unterminated character class")
        re.compile("".join(out))
    except ValueError as error:
        return str(error)
    except re.error as error:
        return error.msg
    return None


def table_rows(
    value: dict[str, Any], columns: list[dict[str, Any]] | None, context: str
) -> None:
    if columns is None:
        fail(context, "a table value requires declared columns")
    declared = {column["id"]: column for column in columns}
    for index, row in enumerate(list_value(value["value"], f"{context}.value")):
        row_context = f"{context}.value[{index}]"
        row = object_value(row, row_context)
        for column_id, cell in row.items():
            column = declared.get(column_id)
            if column is None:
                fail(row_context, f"unknown column {column_id!r}")
            cell_context = f"{row_context}[{column_id!r}]"
            checked = parameter_value(
                cell, COLUMN_VALUE_KINDS[column["kind"]], cell_context
            )
            if column["kind"] == "textPattern" and not well_formed_pattern(
                checked["value"]
            ):
                fail(cell_context, "text pattern ends with an unpaired backslash")
        missing = sorted(
            column_id
            for column_id, column in declared.items()
            if column["required"] and column_id not in row
        )
        if missing:
            fail(row_context, f"missing required columns {missing}")


class TableFileRefused(ValueError):
    """Why a table file's bytes were refused."""


def table_file_path_error(path: str) -> str | None:
    """Why `path` is no package-relative table file path, if it is none.

    Mirrors the engine: relative to the package root, `/`-separated,
    without empty, `.` or `..` segments, and free of backslashes, `:` and NUL.
    """
    if (
        not path
        or path.startswith("/")
        or any(character in path for character in "\\:\0")
        or any(segment in {"", ".", ".."} for segment in path.split("/"))
    ):
        return (
            "the path must be relative to the package root, `/`-separated, "
            "without empty, `.` or `..` segments"
        )
    return None


def table_file_reference(value: dict[str, Any], context: str) -> dict[str, Any]:
    """Check a `tableFile` value's own shape, as the engine loads it.

    The path is package-relative and names a `.csv` file, or an `.xlsx`
    workbook with the `sheet` to take; `sha256` is 64 lowercase hex digits;
    `columns` declares at least one column, each with a distinct id and a
    distinct non-empty header (its id when omitted), a kind other than
    `selector`, and a non-blank `unit` exactly when it is a quantity.
    """
    exact_keys(value, TABLE_FILE_KEYS, {"sheet"}, context)
    path = value["path"]
    if type(path) is not str:
        fail(context, "path must be a string")
    reason = table_file_path_error(path)
    if reason is not None:
        fail(context, reason)
    extension = path.rpartition(".")[2] if "." in path else None
    sheet = value.get("sheet")
    if "sheet" in value and (type(sheet) is not str or not sheet):
        fail(context, "sheet must be a non-empty string")
    if extension == "csv" and sheet is not None:
        fail(context, "a CSV file has no sheets; omit `sheet`")
    if extension == "xlsx" and sheet is None:
        fail(context, "name the workbook's `sheet` to take")
    if extension not in {"csv", "xlsx"}:
        fail(context, "the file is neither a `.csv` file nor an `.xlsx` workbook")
    if type(value["sha256"]) is not str or not SHA256_HEX.fullmatch(value["sha256"]):
        fail(context, "sha256 must be 64 lowercase hexadecimal digits")
    columns = list_value(value["columns"], f"{context}.columns")
    if not columns:
        fail(context, "no columns are declared")
    table_file_columns(columns, context)
    return value


def table_file_columns(columns: list[Any], context: str) -> None:
    """Check a table file's declared `columns`: each with a distinct id and a
    distinct non-empty header (its id when omitted), a kind other than
    `selector`, and a non-blank `unit` exactly when it is a quantity."""
    ids: set[str] = set()
    headers: set[str] = set()
    for index, column in enumerate(columns):
        column_context = f"{context}.columns[{index}]"
        column = object_value(column, column_context)
        exact_keys(column, {"id", "kind"}, {"header", "unit"}, column_context)
        column_id = column["id"]
        if type(column_id) is not str:
            fail(column_context, "id must be a string")
        if "header" in column and type(column["header"]) is not str:
            fail(column_context, "header must be a string")
        header = column.get("header", column_id)
        if column_id in ids:
            fail(column_context, f"column {column_id!r} is declared twice")
        ids.add(column_id)
        if header in headers:
            fail(column_context, f"two columns are headed {header!r}")
        headers.add(header)
        if not header:
            fail(column_context, f"column {column_id!r} has an empty header")
        kind = column["kind"]
        if type(kind) is not str or kind not in COLUMN_VALUE_KINDS:
            fail(column_context, "invalid column kind")
        if kind == "selector":
            fail(
                column_context,
                f"column {column_id!r} is a selector column, which a file cannot hold",
            )
        unit = column.get("unit")
        if "unit" in column and type(unit) is not str:
            fail(column_context, "unit must be a string")
        if kind == "quantity":
            if unit is None:
                fail(column_context, f"quantity column {column_id!r} declares no unit")
            if not unit.strip(TRIMMED):
                fail(column_context, f"quantity column {column_id!r} has a blank unit")
        elif unit is not None:
            fail(
                column_context,
                f"column {column_id!r} declares a unit but is not a quantity column",
            )


def bind_table_file(
    value: dict[str, Any],
    columns: list[dict[str, Any]] | None,
    context: str,
    asset_root: Path | None,
) -> list[dict[str, Any]]:
    """Bind a checked `tableFile` value to the table it fills and return its
    rows, as the engine binds a loaded one.

    Every declared column is one of the table's, of the same kind, and every
    required column of the table is declared. The file must lie inside the
    package (`asset_root`), be at most 10 MB, and have the declared SHA-256;
    its rows are then taken as the engine takes them and bound exactly as the
    same rows written inline.
    """
    if columns is None:
        fail(context, "a table value requires declared columns")
    table = {column["id"]: column for column in columns}
    for column in value["columns"]:
        trusted = table.get(column["id"])
        if trusted is None:
            fail(context, f"{column['id']!r} is not a column of the table")
        if trusted["kind"] != column["kind"]:
            fail(
                context,
                f"column {column['id']!r} is declared {column['kind']} but the "
                f"table's is {trusted['kind']}",
            )
    declared = {column["id"] for column in value["columns"]}
    for column in columns:
        if column["required"] and column["id"] not in declared:
            fail(context, f"the table's required column {column['id']!r} is not declared")
    if asset_root is None:
        fail(context, "package asset root is required for table files")
    path = value["path"]
    root = asset_root.resolve()
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        fail(context, f"table file {path!r} is missing or escapes the package")
    if candidate.stat().st_size > TABLE_FILE_LIMIT_BYTES:
        fail(context, f"table file {path!r} is larger than {TABLE_FILE_LIMIT_BYTES} bytes")
    data = candidate.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != value["sha256"]:
        fail(
            context,
            f"table file {path!r}: the file's SHA-256 is {digest}, not the "
            f"declared {value['sha256']}",
        )
    try:
        rows = table_file_rows(data, path, value.get("sheet"), value["columns"])
    except TableFileRefused as error:
        fail(context, f"table file {path!r}: {error}")
    table_rows({"value": rows}, columns, f"{context}.rows")
    return rows


def table_file_rows(
    data: bytes, path: str, sheet: str | None, columns: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The rows of a checked table file, each cell as the value it fills.

    Mirrors the engine: the first row that is not blank is the header, and
    every header names a declared column (by its `header`, its id when
    omitted) once, and every declared column is named. Every later row that
    is not blank is a table row: an empty cell leaves its column out, any
    other cell is taken as its column's kind.
    """
    grid = csv_grid(data) if sheet is None else xlsx_grid(data, sheet)
    rows = [(number, cells) for number, cells in grid if any(cells)]
    if not rows:
        raise TableFileRefused("the file has no header row")
    (_, header), body = rows[0], rows[1:]
    by_header = {column.get("header", column["id"]): column for column in columns}
    order = []
    for name in header:
        if any(column is by_header.get(name) for column in order):
            raise TableFileRefused(f"the header names column {name!r} twice")
        if name not in by_header:
            raise TableFileRefused(
                f"the header names column {name!r}, which is not declared"
            )
        order.append(by_header[name])
    for name in by_header:
        if name not in header:
            raise TableFileRefused(
                f"the declared column {name!r} is missing from the header"
            )
    table: list[dict[str, Any]] = []
    for number, cells in body:
        if len(cells) > len(order):
            raise TableFileRefused(
                f"row {number} has {len(cells)} cells; the header has {len(order)}"
            )
        row: dict[str, Any] = {}
        for cell, column in zip(cells, order):
            if not cell:
                continue
            try:
                row[column["id"]] = table_file_cell(cell, column)
            except TableFileRefused as error:
                header_name = column.get("header", column["id"])
                raise TableFileRefused(
                    f"row {number} column {header_name!r}: {error}"
                ) from None
        table.append(row)
    return table


def table_file_cell(cell: str, column: dict[str, Any]) -> dict[str, Any]:
    """One cell as the value of its column's kind: a `number` or `quantity`
    a finite decimal number (a quantity in the declared unit), an `integer` a
    whole 64-bit number, a `boolean` `true` or `false`, any other kind its
    text, which binding then checks as any inline cell of that kind."""
    kind = column["kind"]

    def number() -> float:
        if DECIMAL.fullmatch(cell) is None or not math.isfinite(float(cell)):
            raise TableFileRefused(f"{cell!r} is not a number")
        return float(cell)

    if kind == "number":
        return {"type": "number", "value": number()}
    if kind == "quantity":
        return {"type": "quantity", "value": number(), "unit": column["unit"]}
    if kind == "integer":
        if INTEGER_LITERAL.fullmatch(cell) is None or not (
            -(2**63) <= int(cell) < 2**63
        ):
            raise TableFileRefused(f"{cell!r} is not a whole number")
        return {"type": "integer", "value": int(cell)}
    if kind == "boolean":
        if cell not in {"true", "false"}:
            raise TableFileRefused(f"{cell!r} is neither 'true' nor 'false'")
        return {"type": "boolean", "value": cell == "true"}
    return {"type": COLUMN_VALUE_KINDS[kind], "value": cell}


def csv_grid(data: bytes) -> list[tuple[int, list[str]]]:
    """The records of an RFC 4180 CSV file with their one-based numbers.

    Mirrors the engine: UTF-8, a leading byte order mark dropped, fields
    separated by commas and optionally double-quoted with `""` for a quote,
    records ended by CRLF, LF or CR. Every record that is not blank has as
    many fields as the first such record.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise TableFileRefused("the file is not UTF-8 text") from None
    text = text.removeprefix("\ufeff")
    records: list[tuple[int, list[str]]] = []
    record: list[str] = []
    field: list[str] = []
    quoted = closed = started = False
    index = 0

    def end() -> None:
        record.append("".join(field))
        field.clear()
        records.append((len(records) + 1, record.copy()))
        record.clear()

    while index < len(text):
        character = text[index]
        index += 1
        number = len(records) + 1
        if quoted:
            if character == '"':
                if text[index : index + 1] == '"':
                    index += 1
                    field.append('"')
                else:
                    quoted, closed = False, True
            else:
                field.append(character)
            continue
        if character == '"' and not started:
            quoted = started = True
        elif character == ",":
            record.append("".join(field))
            field.clear()
            closed = started = False
        elif character in "\r\n":
            if character == "\r" and text[index : index + 1] == "\n":
                index += 1
            end()
            closed = started = False
        elif character == '"':
            raise TableFileRefused(f"row {number}: a quote inside an unquoted field")
        elif closed:
            raise TableFileRefused(f"row {number}: text after a closing quote")
        else:
            field.append(character)
            started = True
    if quoted:
        raise TableFileRefused(f"row {len(records) + 1}: a quoted field is not closed")
    if started or record:
        end()
    width = next((len(cells) for _, cells in records if any(cells)), 0)
    for number, cells in records:
        if len(cells) != width and any(cells):
            raise TableFileRefused(
                f"row {number} has {len(cells)} fields; the header has {width}"
            )
    return records


def walk_xml(text: str, on: Any) -> None:
    """Walk workbook XML, calling `on` with `("open", name, attributes)`,
    `("close", name)` and `("text", text)` by local name. A document type or
    a processing instruction is refused, as the engine refuses them."""

    def local(name: str) -> str:
        return name.rpartition(":")[2]

    def refuse(*_: Any) -> None:
        raise TableFileRefused(
            "workbook XML declares a document type or processing instruction"
        )

    parser = expat.ParserCreate()
    parser.StartElementHandler = lambda name, attributes: on(
        ("open", local(name), {local(key): item for key, item in attributes.items()})
    )
    parser.EndElementHandler = lambda name: on(("close", local(name)))
    parser.CharacterDataHandler = lambda content: on(("text", content))
    parser.StartDoctypeDeclHandler = refuse
    parser.ProcessingInstructionHandler = refuse
    try:
        parser.Parse(text, True)
    except expat.ExpatError as error:
        raise TableFileRefused(f"malformed workbook XML: {error}") from None


def xlsx_grid(data: bytes, sheet: str) -> list[tuple[int, list[str]]]:
    """The rows of the sheet `sheet` of an xlsx workbook, each cell as text.

    Mirrors the engine: a shared or inline string as written, a number as
    its literal, a boolean as `true` or `false`; a formula or an error cell
    is refused rather than taken from its cached result.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as error:
        raise TableFileRefused(f"the workbook cannot be opened: {error}") from None

    def member(name: str) -> str | None:
        try:
            with archive.open(name) as handle:
                content = handle.read(TABLE_FILE_LIMIT_BYTES + 1)
        except KeyError:
            return None
        except (zipfile.BadZipFile, ValueError, NotImplementedError) as error:
            raise TableFileRefused(f"workbook member {name!r}: {error}") from None
        if len(content) > TABLE_FILE_LIMIT_BYTES:
            raise TableFileRefused(
                f"workbook member {name!r} unpacks to more than "
                f"{TABLE_FILE_LIMIT_BYTES} bytes"
            )
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            raise TableFileRefused(f"workbook member {name!r} is not UTF-8") from None

    def required(name: str) -> str:
        content = member(name)
        if content is None:
            raise TableFileRefused(f"the workbook has no {name!r}")
        return content

    names: list[str] = []
    found: list[str | None] = [None]

    def on_sheet(event: tuple) -> None:
        if event[0] == "open" and event[1] == "sheet":
            label = event[2].get("name", "")
            if label == sheet:
                found[0] = event[2].get("id")
            names.append(label)

    walk_xml(required("xl/workbook.xml"), on_sheet)
    relationship = found[0]
    if relationship is None:
        raise TableFileRefused(
            f"the workbook has no sheet {sheet!r} (its sheets: {', '.join(names)})"
        )
    target: list[str | None] = [None]

    def on_relationship(event: tuple) -> None:
        if (
            event[0] == "open"
            and event[1] == "Relationship"
            and event[2].get("Id") == relationship
        ):
            target[0] = event[2].get("Target")

    walk_xml(required("xl/_rels/workbook.xml.rels"), on_relationship)
    if target[0] is None:
        raise TableFileRefused(f"the workbook has no relationship {relationship!r}")
    sheet_path = target[0]
    if table_file_path_error(sheet_path.lstrip("/")) is not None:
        raise TableFileRefused(f"the workbook's sheet lies at {sheet_path!r}, outside it")
    sheet_path = sheet_path[1:] if sheet_path.startswith("/") else f"xl/{sheet_path}"
    shared_xml = member("xl/sharedStrings.xml")
    shared = [] if shared_xml is None else shared_strings(shared_xml)
    return sheet_cells(required(sheet_path), shared)


def shared_strings(text: str) -> list[str]:
    """The shared strings, each the text of its runs, phonetic runs left out."""
    strings: list[str] = []
    state: dict[str, Any] = {"item": None, "phonetic": 0, "text": False}

    def on(event: tuple) -> None:
        if event[0] == "open":
            if event[1] == "si":
                state["item"] = []
            elif event[1] == "rPh":
                state["phonetic"] += 1
            elif event[1] == "t":
                state["text"] = True
        elif event[0] == "close":
            if event[1] == "si":
                strings.append("".join(state["item"] or []))
                state["item"] = None
            elif event[1] == "rPh":
                state["phonetic"] = max(0, state["phonetic"] - 1)
            elif event[1] == "t":
                state["text"] = False
        elif state["item"] is not None and state["text"] and not state["phonetic"]:
            state["item"].append(event[1])

    walk_xml(text, on)
    return strings


def column_index(reference: str) -> int:
    """The zero-based column of a cell reference such as `B3`."""
    letters = re.match(r"[A-Z]*", reference).group(0)
    if not letters or len(letters) > 3:
        raise TableFileRefused(f"cell reference {reference!r} names no column")
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def cell_text(cell: dict[str, Any], shared: list[str]) -> str:
    """One worksheet cell as text, by its type `t`."""
    if cell["formula"]:
        raise TableFileRefused("a formula; store its value instead")
    value = "".join(cell["value"] or [])
    kind = cell["kind"]
    if kind == "s":
        if not value:
            return ""
        stripped = value.strip()
        if stripped.isdigit() and stripped.isascii() and int(stripped) < len(shared):
            return shared[int(stripped)]
        raise TableFileRefused(f"shared string {value!r} does not exist")
    if kind == "inlineStr":
        return "".join(cell["inline"] or [])
    if kind in {"str", "d", "n"}:
        return value
    if kind == "b":
        if value in {"1", "0", ""}:
            return {"1": "true", "0": "false", "": ""}[value]
        raise TableFileRefused(f"{value!r} is not a boolean")
    if kind == "e":
        raise TableFileRefused(f"an error value {value!r}")
    raise TableFileRefused(f"an unknown cell type {kind!r}")


def sheet_cells(text: str, shared: list[str]) -> list[tuple[int, list[str]]]:
    """The rows of a worksheet by row number, each cell as text."""
    rows: dict[int, list[str]] = {}
    state: dict[str, Any] = {"row": 0, "cell": None, "slot": None, "next": 0}

    def on(event: tuple) -> None:
        cell = state["cell"]
        if event[0] == "open":
            name, attributes = event[1], event[2]
            if name == "row":
                number = attributes.get("r")
                if number is None:
                    state["row"] += 1
                elif number.isdigit() and number.isascii() and int(number) > 0:
                    state["row"] = int(number)
                else:
                    raise TableFileRefused(f"row number {number!r} is not a row")
                state["next"] = 0
            elif name == "c":
                reference = attributes.get("r")
                column = state["next"] if reference is None else column_index(reference)
                state["next"] = column + 1
                state["cell"] = {
                    "kind": attributes.get("t", "n"),
                    "column": column,
                    "value": None,
                    "inline": None,
                    "formula": False,
                }
            elif name == "v":
                state["slot"] = "value"
            elif name == "t" and cell is not None:
                state["slot"] = "inline"
            elif name == "f" and cell is not None:
                cell["formula"] = True
        elif event[0] == "text":
            if cell is not None and state["slot"] is not None:
                if cell[state["slot"]] is None:
                    cell[state["slot"]] = []
                cell[state["slot"]].append(event[1])
        elif event[1] in {"v", "t"}:
            state["slot"] = None
        elif event[1] == "c" and cell is not None:
            state["cell"] = None
            try:
                content = cell_text(cell, shared)
            except TableFileRefused as error:
                raise TableFileRefused(
                    f"row {state['row']} column {cell['column'] + 1}: {error}"
                ) from None
            row = rows.setdefault(max(state["row"], 1), [])
            if len(row) <= cell["column"]:
                row.extend([""] * (cell["column"] + 1 - len(row)))
            row[cell["column"]] = content

    walk_xml(text, on)
    return sorted(rows.items())


def offset_error(offset: str) -> str | None:
    """Why `offset` (`Z` or `±hh:mm`) is not a UTC offset, if it is not."""
    if offset != "Z":
        hours, minutes = int(offset[1:3]), int(offset[4:6])
        if minutes >= 60 or hours * 60 + minutes > 14 * 60:
            return "an offset is at most 14:00"
        if offset == "-00:00":
            return "-00:00 states no offset"
    return None


def day_error(year: int, month: int, day: int) -> str | None:
    """Why `year-month-day` is not a real day of the proleptic Gregorian calendar."""
    if not 1 <= month <= 12:
        return "no such day"
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    if month == 2:
        days = 29 if leap else 28
    elif month in {4, 6, 9, 11}:
        days = 30
    else:
        days = 31
    if not 1 <= day <= days:
        return "no such day"
    return None


def date_literal_error(literal: str) -> str | None:
    """Why `literal` is not a real `YYYY-MM-DD` day in 0000 to 9999, if it is not.

    Mirrors the engine: the day may state a time zone, `Z` or `±hh:mm` of at
    most 14 hours, as `xs:date` allows; `-00:00` states no time zone.
    """
    match = DATE_LITERAL.fullmatch(literal)
    if match is None:
        return "expected YYYY-MM-DD and an optional time zone Z or ±hh:mm"
    year, month, day, offset = match.groups()
    if (reason := day_error(int(year), int(month), int(day))) is not None:
        return reason
    return None if offset is None else offset_error(offset)


def date_time_literal_error(literal: str) -> str | None:
    """Why `literal` is not a date-time with a UTC offset, if it is not.

    Mirrors the engine: a real day, a time of day from 00:00:00 to 23:59:59
    (no 24:00, no leap second), up to nine fraction digits, and an offset of
    `Z` or `±hh:mm` of at most 14 hours; `-00:00` states no offset.
    """
    match = DATE_TIME_LITERAL.fullmatch(literal)
    if match is None:
        return "expected YYYY-MM-DDThh:mm:ss[.f{1,9}] and an offset Z or ±hh:mm"
    day, hour, minute, second, offset = match.groups()
    if (reason := day_error(*(int(part) for part in day.split("-")))) is not None:
        return reason
    if (reason := offset_error(offset)) is not None:
        return reason
    if int(hour) == 24:
        return "24:00 is refused; write 00:00 of the next day"
    if int(second) == 60:
        return "a leap second cannot be ordered"
    if int(hour) > 23 or int(minute) > 59 or int(second) > 59:
        return "no such time of day"
    return None


def parameter_value(
    value: Any,
    expected_kind: str | None,
    context: str,
    columns: list[dict[str, Any]] | None = None,
    asset_root: Path | None = None,
) -> dict[str, Any]:
    value = object_value(value, context)
    kind = value.get("type")
    if kind == TABLE_FILE and expected_kind == "table":
        # A table's rows may instead come from a data file in the package.
        table_file_reference(value, context)
        bind_table_file(value, columns, context, asset_root)
        return value
    if (
        type(kind) is not str
        or kind not in VALUE_KINDS
        or (expected_kind is not None and kind != expected_kind)
    ):
        fail(
            context, f"expected {expected_kind or 'known'} value variant, got {kind!r}"
        )
    optional = {"propertySet"} if kind == "propertyReference" else set()
    exact_keys(value, VALUE_KEYS[kind], optional, context)
    if kind == "objectTypeReference":
        if (
            type(value["objectType"]) is not str
            or not QUALIFIED_ID.fullmatch(value["objectType"])
            or type(value["includeSubtypes"]) is not bool
        ):
            fail(context, "invalid object-type reference")
        return value
    if kind == "propertyReference":
        if "propertySet" in value and (
            type(value["propertySet"]) is not str
            or not QUALIFIED_ID.fullmatch(value["propertySet"])
        ):
            fail(context, "propertySet must be a qualified identifier")
        reason = property_name_error(value.get("propertySet"), value["property"])
        if reason is not None:
            fail(context, reason)
        return value
    item = value["value"]
    if kind == "selector":
        validate_selector(item, f"{context}.value")
        return value
    if kind == "table":
        table_rows(value, columns, context)
        return value
    if kind in {"string", "enum", "reference"}:
        if type(item) is not str:
            fail(context, "value must be a string")
        if kind == "enum" and not IDENTIFIER.fullmatch(item):
            fail(context, "invalid enum identifier")
        if kind == "reference" and not QUALIFIED_ID.fullmatch(item):
            fail(context, "invalid qualified reference")
    elif kind == "boolean":
        if type(item) is not bool:
            fail(context, "value must be a boolean")
    elif kind == "integer":
        if type(item) is not int:
            fail(context, "value must be an integer")
    elif kind in TEMPORAL_VALUE_KINDS:
        if type(item) is not str:
            fail(context, "value must be a string")
        if kind == "date":
            reason = date_literal_error(item)
            expected = "an ISO 8601 date (YYYY-MM-DD)"
        else:
            reason = date_time_literal_error(item)
            expected = "an ISO 8601 date-time with a UTC offset"
        if reason is not None:
            fail(context, f"{item!r} is not {expected}: {reason}")
    elif kind in {"number", "quantity"}:
        if type(item) not in {int, float} or not math.isfinite(item):
            fail(context, "value must be a finite number")
        if kind == "quantity" and (type(value["unit"]) is not str or not value["unit"]):
            fail(context, "quantity unit must be non-empty")
    else:
        items = list_value(item, f"{context}.value")
        for index, entry in enumerate(items):
            if type(entry) is not str:
                fail(f"{context}.value[{index}]", "expected string")
            if kind == "referenceList" and not QUALIFIED_ID.fullmatch(entry):
                fail(f"{context}.value[{index}]", "invalid qualified reference")
    return value


def resolve_object_type_reference(
    value: dict[str, Any], object_types: dict[str, dict[str, Any]], context: str
) -> None:
    if (
        value["type"] == "objectTypeReference"
        and value["objectType"] not in object_types
    ):
        fail(context, f"unknown object-type concept {value['objectType']!r}")


def resolve_property_reference(
    value: dict[str, Any],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    context: str,
    expected_value_kind: str | None = None,
    classifications: dict[str, dict[str, Any]] | None = None,
) -> None:
    if value["type"] != "propertyReference":
        return
    property_set = value.get("propertySet")
    if property_set in DERIVED_PROPERTY_SETS:
        # Derived sets name engine or ruleset vocabulary, never a concept.
        kind = derived_property_kind(
            property_set, value["property"], classifications or {}, context
        )
        if expected_value_kind is not None and kind != expected_value_kind:
            fail(
                context,
                f"derived property has value kind {kind!r}, expected "
                f"{expected_value_kind!r}",
            )
        return
    if value["property"] not in properties:
        fail(context, f"unknown property concept {value['property']!r}")
    if (
        expected_value_kind is not None
        and properties[value["property"]]["valueKind"] != expected_value_kind
    ):
        fail(
            context,
            f"property concept has value kind {properties[value['property']]['valueKind']!r}, expected {expected_value_kind!r}",
        )
    # Reserved sets are engine vocabulary and bind to themselves; the property
    # in them is still a concept.
    if (
        "propertySet" in value
        and value["propertySet"] not in RESERVED_PROPERTY_SETS
        and value["propertySet"] not in property_sets
    ):
        fail(context, f"unknown property-set concept {value['propertySet']!r}")


def resolve_selector_value(
    value: dict[str, Any],
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    context: str,
    classifications: dict[str, dict[str, Any]] | None = None,
    groupings: set[str] | None = None,
    relations: set[str] | None = None,
) -> None:
    if value["type"] == "selector":
        validate_selector(
            value["value"],
            context,
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
    elif value["type"] == "table":
        # Selector cells name concepts like any selector parameter.
        for index, row in enumerate(value["value"]):
            for column_id, cell in row.items():
                resolve_selector_value(
                    cell,
                    object_types,
                    properties,
                    property_sets,
                    f"{context}.value[{index}][{column_id!r}]",
                    classifications,
                    groupings,
                    relations,
                )


def table_columns(value: Any, context: str) -> list[dict[str, Any]]:
    columns = list_value(value, context)
    if not columns:
        fail(context, "a table declares at least one column")
    seen: set[str] = set()
    for index, column in enumerate(columns):
        column_context = f"{context}[{index}]"
        column = object_value(column, column_context)
        exact_keys(
            column,
            {"id", "name", "kind", "required"},
            {"description", "unitDimension"},
            column_context,
        )
        column_id = column["id"]
        if type(column_id) is not str or not IDENTIFIER.fullmatch(column_id):
            fail(column_context, "invalid column id")
        if column_id in seen:
            fail(column_context, f"duplicate column id {column_id!r}")
        seen.add(column_id)
        localized_text(column["name"], f"{column_context}.name")
        if "description" in column:
            localized_text(column["description"], f"{column_context}.description")
        if (
            type(column["kind"]) is not str
            or column["kind"] not in COLUMN_VALUE_KINDS
            or type(column["required"]) is not bool
        ):
            fail(column_context, "invalid column kind or required flag")
        dimension = column.get("unitDimension")
        if column["kind"] == "quantity":
            if type(dimension) is not str or not dimension:
                fail(column_context, "quantity columns require unitDimension")
        elif "unitDimension" in column:
            fail(column_context, "unitDimension is only valid for quantity columns")
    return columns


def validate_parameter_definition(
    value: Any, context: str, asset_root: Path | None = None
) -> dict[str, Any]:
    value = object_value(value, context)
    exact_keys(
        value,
        {"id", "name", "kind", "required", "allowedValues"},
        {
            "defaultValue",
            "unitDimension",
            "description",
            "referencedValueKind",
            "citations",
            "columns",
        },
        context,
    )
    if type(value["id"]) is not str or not IDENTIFIER.fullmatch(value["id"]):
        fail(context, "invalid parameter id")
    localized_text(value["name"], f"{context}.name")
    if "description" in value:
        localized_text(value["description"], f"{context}.description")
    kind = value["kind"]
    if (
        type(kind) is not str
        or kind not in VALUE_KINDS
        or type(value["required"]) is not bool
    ):
        fail(context, "invalid parameter kind or required flag")
    dimension = value.get("unitDimension")
    if kind == "quantity":
        if type(dimension) is not str or not dimension:
            fail(context, "quantity parameters require unitDimension")
    elif "unitDimension" in value:
        fail(context, "unitDimension is only valid for quantity parameters")
    referenced_kind = value.get("referencedValueKind")
    if referenced_kind is not None and (
        kind != "propertyReference" or referenced_kind not in PROPERTY_VALUE_KINDS
    ):
        fail(
            context,
            "referencedValueKind requires a propertyReference parameter and valid value kind",
        )
    columns = None
    if kind == "table":
        if "columns" not in value:
            fail(context, "table parameters require columns")
        columns = table_columns(value["columns"], f"{context}.columns")
        if value["allowedValues"] != []:
            fail(context, "allowedValues is not valid for table parameters")
    elif "columns" in value:
        fail(context, "columns are only valid for table parameters")
    if "defaultValue" in value:
        parameter_value(
            value["defaultValue"], kind, f"{context}.defaultValue", columns, asset_root
        )
    allowed = list_value(value["allowedValues"], f"{context}.allowedValues")
    seen: set[str] = set()
    for index, allowed_value in enumerate(allowed):
        validated = parameter_value(
            allowed_value, kind, f"{context}.allowedValues[{index}]"
        )
        marker = json.dumps(validated, sort_keys=True, separators=(",", ":"))
        if marker in seen:
            fail(context, "duplicate allowed value")
        seen.add(marker)
    if "defaultValue" in value and allowed and value["defaultValue"] not in allowed:
        fail(context, "defaultValue is outside allowedValues")
    return value


def external_names(value: Any, context: str) -> None:
    entries = list_value(value, context)
    if not entries:
        fail(context, "at least one external name is required")
    systems: set[str] = set()
    for index, entry in enumerate(entries):
        entry_context = f"{context}[{index}]"
        entry = object_value(entry, entry_context)
        exact_keys(entry, {"typeSystem", "name"}, set(), entry_context)
        system = entry["typeSystem"]
        if type(system) is not str or not QUALIFIED_ID.fullmatch(system):
            fail(entry_context, "invalid type system")
        if type(entry["name"]) is not str or not entry["name"]:
            fail(entry_context, "external name must be non-empty")
        if system in systems:
            fail(entry_context, "duplicate type-system binding")
        systems.add(system)


def validate_concept(
    value: Any, expected_id: str, context: str, *, property_definition: bool
) -> dict[str, Any]:
    value = object_value(value, context)
    required = {"id", "name", "externalNames"}
    if property_definition:
        required.add("valueKind")
    optional = (
        {"description", "unitDimension", "citations"}
        if property_definition
        else {"description", "citations"}
    )
    exact_keys(value, required, optional, context)
    if value["id"] != expected_id or not QUALIFIED_ID.fullmatch(expected_id):
        fail(context, "map key and concept id must match")
    localized_text(value["name"], f"{context}.name")
    if "description" in value:
        localized_text(value["description"], f"{context}.description")
    if property_definition:
        value_kind = value["valueKind"]
        if value_kind not in PROPERTY_VALUE_KINDS:
            fail(context, "invalid property value kind")
        unit_dimension = value.get("unitDimension")
        if value_kind == "quantity":
            if type(unit_dimension) is not str or not QUALIFIED_ID.fullmatch(
                unit_dimension
            ):
                fail(context, "quantity properties require a qualified unitDimension")
        elif unit_dimension is not None:
            fail(context, "unitDimension is only valid for quantity properties")
    external_names(value["externalNames"], f"{context}.externalNames")
    return value


def validate_definition_document(
    value: Any, context: str, *, asset_root: Path | None = None
) -> tuple[
    str,
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    value = object_value(value, context)
    exact_keys(
        value,
        {
            "schemaVersion",
            "package",
            "sources",
            "objectTypes",
            "properties",
            "propertySets",
            "definitions",
        },
        set(),
        context,
    )
    package_id = package_metadata(value["package"], f"{context}.package")
    sources = validate_sources(value["sources"], f"{context}.sources")
    object_types = object_value(value["objectTypes"], f"{context}.objectTypes")
    properties = object_value(value["properties"], f"{context}.properties")
    property_sets = object_value(value["propertySets"], f"{context}.propertySets")
    definitions = object_value(value["definitions"], f"{context}.definitions")
    if not (object_types or properties or property_sets or definitions):
        fail(context, "definition package is empty")
    for object_type_id, object_type in object_types.items():
        checked = validate_concept(
            object_type,
            object_type_id,
            f"{context}.objectTypes[{object_type_id!r}]",
            property_definition=False,
        )
        validate_citations(
            checked.get("citations", []),
            sources,
            f"{context}.objectTypes[{object_type_id!r}].citations",
        )
    for property_id, property_definition in properties.items():
        checked = validate_concept(
            property_definition,
            property_id,
            f"{context}.properties[{property_id!r}]",
            property_definition=True,
        )
        validate_citations(
            checked.get("citations", []),
            sources,
            f"{context}.properties[{property_id!r}].citations",
        )
    for property_set_id, property_set in property_sets.items():
        checked = validate_concept(
            property_set,
            property_set_id,
            f"{context}.propertySets[{property_set_id!r}]",
            property_definition=False,
        )
        validate_citations(
            checked.get("citations", []),
            sources,
            f"{context}.propertySets[{property_set_id!r}].citations",
        )
    for definition_id, definition in definitions.items():
        definition_context = f"{context}.definitions[{definition_id!r}]"
        definition = object_value(definition, definition_context)
        exact_keys(
            definition,
            {"id", "name", "capability", "parameters", "tags"},
            {"description", "citations"},
            definition_context,
        )
        if definition_id != definition["id"] or not QUALIFIED_ID.fullmatch(
            definition_id
        ):
            fail(definition_context, "map key and definition id must match")
        localized_text(definition["name"], f"{definition_context}.name")
        if "description" in definition:
            localized_text(
                definition["description"], f"{definition_context}.description"
            )
        if type(definition["capability"]) is not str or not QUALIFIED_ID.fullmatch(
            definition["capability"]
        ):
            fail(definition_context, "invalid capability id")
        parameters = object_value(
            definition["parameters"], f"{definition_context}.parameters"
        )
        for parameter_id, parameter in parameters.items():
            validated = validate_parameter_definition(
                parameter,
                f"{definition_context}.parameters[{parameter_id!r}]",
                asset_root,
            )
            if parameter_id != validated["id"]:
                fail(definition_context, "parameter map key and id must match")
            validate_citations(
                validated.get("citations", []),
                sources,
                f"{definition_context}.parameters[{parameter_id!r}].citations",
            )
        string_list(definition["tags"], f"{definition_context}.tags")
        validate_citations(
            definition.get("citations", []),
            sources,
            f"{definition_context}.citations",
        )
    return package_id, definitions, object_types, properties, property_sets


def validate_property_comparison(
    value: dict[str, Any], context: str, property_kind: str | None
) -> None:
    """Check a property or property-pattern selector's comparison fields.

    `property_kind` is the compared property's value kind when a concept
    declares it, else `None`, which leaves kind-dependent checks to the
    checking application.
    """
    operator = value["operator"]
    if type(operator) is not str or operator not in SELECTOR_OPERATORS:
        fail(context, "invalid property selector")
    for flag in ("caseSensitive", "trim"):
        if flag in value and type(value[flag]) is not bool:
            fail(context, f"{flag} must be a boolean")
    if "quantifier" in value and (
        type(value["quantifier"]) is not str or value["quantifier"] not in QUANTIFIERS
    ):
        fail(context, "quantifier must be 'any' or 'all'")
    presence = operator in PRESENCE_OPERATORS
    if presence and "quantifier" in value:
        fail(context, f"{operator} selector must not have a quantifier")
    if "precision" in value and (
        type(value["precision"]) is not str
        or value["precision"] not in TEMPORAL_PRECISIONS
    ):
        fail(context, "precision must be 'day'")
    if presence and "value" in value:
        fail(context, f"{operator} selector must not have a value")
    if not presence and "value" not in value:
        fail(context, "comparison selector requires a value")
    if property_kind in LIST_ELEMENT_KINDS and not presence:
        if "quantifier" not in value:
            fail(context, "comparing a list-valued property requires a quantifier")
        # A quantified comparison tests each element on its own.
        property_kind = LIST_ELEMENT_KINDS[property_kind]
    compared_kind: str | None = None
    if "value" in value:
        if operator in TEXT_PATTERN_OPERATORS:
            parameter_value(value["value"], "string", f"{context}.value")
            if property_kind is not None and property_kind not in TEXT_VALUE_KINDS:
                fail(context, f"{operator} requires a text property")
            compared_kind = "string"
        elif operator in LIST_OPERATORS:
            checked = parameter_value(value["value"], "stringList", f"{context}.value")
            if property_kind is not None:
                if property_kind not in TEXT_VALUE_KINDS:
                    fail(context, f"{operator} requires a text property")
                # Each element is one candidate for the property's value.
                for index, entry in enumerate(checked["value"]):
                    parameter_value(
                        {"type": property_kind, "value": entry},
                        property_kind,
                        f"{context}.value.value[{index}]",
                    )
            compared_kind = "string"
        else:
            # Day precision reads a date-time as the day it states, so a
            # date and a date-time then compare with each other.
            day_precision = (
                "precision" in value and property_kind in TEMPORAL_VALUE_KINDS
            )
            checked = parameter_value(
                value["value"],
                None if day_precision else property_kind,
                f"{context}.value",
            )
            compared_kind = checked["type"]
            if day_precision and compared_kind not in TEMPORAL_VALUE_KINDS:
                fail(
                    context,
                    f"expected a date or dateTime value, got {compared_kind!r}",
                )
            if (
                operator in ORDERING_OPERATORS
                and compared_kind not in ORDERED_VALUE_KINDS
            ):
                fail(
                    context,
                    f"{operator} requires an integer, number, quantity, "
                    "string, date, or dateTime value",
                )
    if (value.get("caseSensitive") is False or value.get("trim") is True) and (
        presence or compared_kind not in TEXT_VALUE_KINDS
    ):
        fail(context, "caseSensitive and trim apply only to text comparisons")
    if "precision" in value and compared_kind not in TEMPORAL_VALUE_KINDS:
        fail(context, "precision applies only to a date or dateTime value")


def property_name_error(property_set: Any, name: Any) -> str | None:
    """Why `name` cannot name a property in `property_set`, if it cannot.

    A property in a derived set is engine or ruleset vocabulary; any other
    property is a qualified concept ID.
    """
    if type(name) is not str:
        return "property must be a string"
    if property_set == CLASSIFICATION_SET:
        if not name.strip():
            return "a classification id must not be blank"
        _, separator, parameter = name.partition(";")
        if separator and not (
            parameter.startswith("level=")
            and CLASSIFICATION_LEVEL.fullmatch(parameter.removeprefix("level="))
        ):
            return "a classification is read as '<id>' or '<id>;level=<n>'"
        return None
    if property_set == MEASURED_SET:
        return measured_name_error(name)
    if property_set == GROUP_SET:
        return (
            None
            if name in GROUP_NAMES
            else "a derived group states only 'key' and 'members'"
        )
    if not QUALIFIED_ID.fullmatch(name):
        return "property must be a qualified identifier"
    return None


def ascii_lower(text: str) -> str:
    return "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in text
    )


def path_step_error(
    step: Any, relationship_name: re.Pattern[str] = RELATED_PATH_RELATIONSHIP
) -> str | None:
    """Why `step` is no relationship path step, if it is none.

    Mirrors the engine's step grammar:

        step          = relationships [ ":" direction ] [ "+" ]
        relationships = relationship { "|" relationship }
        direction     = "forward" | "backward" | "either"

    One direction, written after the last alternative, applies to all of
    them. An empty alternative, an alternative named twice, or a direction
    inside an alternative is refused. A derived identity keeps its own colon:
    only a colon followed by a direction word ends the last alternative.
    """
    if type(step) is not str:
        return "path step must be a string"
    body = step[:-1] if step.endswith("+") else step
    *alternatives, last = body.split("|")
    relationship, colon, stated = last.rpartition(":")
    if colon and stated in PATH_DIRECTIONS:
        last = relationship
    alternatives.append(last)
    seen: set[str] = set()
    for alternative in alternatives:
        _, colon, stated = alternative.rpartition(":")
        if colon and stated in PATH_DIRECTIONS:
            return (
                f"path step {step!r} states a direction inside {alternative!r}; "
                "one direction follows the last alternative and applies to all"
            )
        if not alternative:
            return f"path step {step!r} names an empty relationship"
        if not (
            relationship_name.fullmatch(alternative)
            or DERIVED_RELATIONSHIP.fullmatch(alternative)
            or DERIVED_GROUP_RELATIONSHIP.fullmatch(alternative)
            or DERIVED_RELATION_RELATIONSHIP.fullmatch(alternative)
            or RELATIONSHIP_KIND.fullmatch(alternative)
        ):
            return f"path step {step!r} must be {PATH_STEP_GRAMMAR}"
        if alternative in seen:
            return f"path step {step!r} names {alternative!r} more than once"
        seen.add(alternative)
    return None


def path_step_names(step: str, relationship: re.Pattern[str]) -> set[str]:
    """The groupings or relations a checked path step's
    `axioval:derived.group;by=<id>` or `axioval:derived.relation;id=<id>`
    alternatives name, as `relationship` captures them."""
    body = step[:-1] if step.endswith("+") else step
    return {
        match.group(1)
        for alternative in body.split("|")
        if (match := relationship.match(alternative)) is not None
    }


def check_path_derived(
    path: list[str], groupings: set[str], relations: set[str], context: str
) -> None:
    """Bind the groupings and relations a checked path names against the
    ruleset's: a group relationship names a grouping, a relation relationship
    a relation the same ruleset declares."""
    for index, step in enumerate(path):
        for grouping in sorted(
            path_step_names(step, DERIVED_GROUP_RELATIONSHIP) - groupings
        ):
            fail(f"{context}[{index}]", f"unknown grouping {grouping!r}")
        for relation in sorted(
            path_step_names(step, DERIVED_RELATION_RELATIONSHIP) - relations
        ):
            fail(f"{context}[{index}]", f"unknown relation {relation!r}")


def measured_name_error(name: str) -> str | None:
    """Why `name` is no name in `axioval:measured`, if it is none.

    Mirrors the engine's parser: a name, ignoring ASCII case and surrounding
    whitespace, then `;`-separated `key=value` parameters. Only
    `bottom_above_level` (`path`, required: `,`-separated related-selector
    steps) and `boundary_area` (`kind`, required, and `plane`, a length of at
    least zero) take parameters.
    """
    base, *parts = name.split(";")
    base = ascii_lower(base.strip(TRIMMED))
    parameters: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            return f"{part!r} is not 'key=value'"
        key, value = part.split("=", 1)
        key = ascii_lower(key.strip(TRIMMED))
        if key in parameters:
            return f"{key!r} is stated twice"
        parameters[key] = value.strip(TRIMMED)
    if base == MEASURED_BOTTOM_ABOVE_LEVEL:
        path = parameters.pop("path", None)
        if path is None:
            return "'bottom_above_level' needs 'path'"
        for step in path.split(","):
            error = path_step_error(step.strip(TRIMMED), MEASURED_PATH_RELATIONSHIP)
            if error is not None:
                return error
    elif base == MEASURED_BOUNDARY_AREA:
        if not parameters.pop("kind", ""):
            return "'boundary_area' needs 'kind'"
        plane = parameters.pop("plane", None)
        if plane is not None and not (
            DECIMAL.fullmatch(plane)
            and math.isfinite(float(plane))
            and float(plane) >= 0
        ):
            return f"'plane' {plane!r} is no length of at least zero"
    elif base not in MEASURED_NAMES:
        return (
            f"{base!r} is not a measured name "
            f"{sorted(MEASURED_NAMES | {MEASURED_BOTTOM_ABOVE_LEVEL, MEASURED_BOUNDARY_AREA})}"
        )
    if parameters:
        return f"{base!r} takes no parameter {next(iter(parameters))!r}"
    return None


CLASSIFICATION_LEVEL = re.compile(r"[1-9][0-9]*")


def classification_property(name: str, context: str) -> tuple[str, int | None]:
    """Split a name in `axioval:classification` into its ID and tree level.

    `<id>` reads the class a classification assigns; `<id>;level=<n>` the
    class at level `n` of a hierarchical classification's tree, `n` a
    positive integer without leading zeros. No other parameter exists.
    """
    classification_id, separator, parameter = name.partition(";")
    if not separator:
        return name, None
    level = parameter.removeprefix("level=")
    if level == parameter:
        fail(context, f"{parameter!r} is not a classification parameter; only 'level=<n>' is")
    if not CLASSIFICATION_LEVEL.fullmatch(level):
        fail(context, f"the level {level!r} is not a positive integer")
    return classification_id, int(level)


def class_levels(classification: dict[str, Any]) -> dict[str, int]:
    """The level of every declared class of a checked hierarchical classification."""
    parents = {
        declared["id"]: declared.get("parent") for declared in classification["classes"]
    }
    levels = {}
    for class_id in parents:
        level, parent = 1, parents[class_id]
        while parent is not None:
            level, parent = level + 1, parents[parent]
        levels[class_id] = level
    return levels


def classification_classes(classification: dict[str, Any]) -> set[str]:
    """The classes of a checked classification: its declared classes, or the
    classes a flat one's rows assign."""
    if "classes" in classification:
        return {declared["id"] for declared in classification["classes"]}
    return {row.get("class") for row in classification["rows"] if type(row) is dict}


def validate_classes(classification: dict[str, Any], context: str) -> None:
    """Check a classification's declared classes as a tree.

    Class IDs and codes are non-blank and distinct, every parent is a declared
    class, parents form no cycle, and every row assigns a declared class.
    """
    classes = list_value(classification["classes"], f"{context}.classes")
    if not classes:
        fail(context, "classes is omitted when empty")
    parents: dict[str, str | None] = {}
    codes: set[str] = set()
    for index, declared in enumerate(classes):
        class_context = f"{context}.classes[{index}]"
        declared = object_value(declared, class_context)
        exact_keys(declared, {"id", "name"}, {"code", "parent"}, class_context)
        for key in ("id", "code", "parent"):
            if key in declared and (
                type(declared[key]) is not str or not declared[key].strip()
            ):
                fail(class_context, f"{key} must be a non-blank string")
        localized_text(declared["name"], f"{class_context}.name")
        if declared["id"] in parents:
            fail(class_context, f"the class {declared['id']!r} is declared twice")
        parents[declared["id"]] = declared.get("parent")
        if "code" in declared:
            if declared["code"] in codes:
                fail(class_context, f"two classes have the code {declared['code']!r}")
            codes.add(declared["code"])
    for index, declared in enumerate(classes):
        class_context = f"{context}.classes[{index}]"
        parent = declared.get("parent")
        if parent is not None and parent not in parents:
            fail(class_context, f"the parent {parent!r} is not a declared class")
        # Walking up reaches a root within as many steps as there are classes,
        # or the parents form a cycle.
        steps = 0
        while parent is not None:
            steps += 1
            if steps > len(parents):
                fail(class_context, f"the parents of {declared['id']!r} form a cycle")
            parent = parents[parent]


def derived_property_kind(
    property_set: str,
    name: str,
    classifications: dict[str, dict[str, Any]],
    context: str,
) -> str | None:
    """Bind a property of a derived set and return its value kind, if known.

    A classification is read by its ID: a string for a first-match
    classification, a list of strings for an all-match one. A measured value
    is a quantity, or an interval the application compares as one. A derived
    group states its `key`, a string, and its `members`, an integer.
    """
    if property_set == GROUP_SET:
        reason = property_name_error(property_set, name)
        if reason is not None:
            fail(context, reason)
        return GROUP_NAMES[name]
    if property_set == MEASURED_SET:
        reason = property_name_error(property_set, name)
        if reason is not None:
            fail(context, reason)
        return "quantity"
    if property_set == CLASSIFICATION_SET:
        classification_id, level = classification_property(name, context)
        classification = classifications.get(classification_id)
        if classification is None:
            fail(context, f"unknown classification {classification_id!r}")
        if level is not None:
            if "classes" not in classification:
                fail(context, f"the flat classification {classification_id!r} has no levels")
            depth = max(class_levels(classification).values())
            if level > depth:
                fail(
                    context,
                    f"the classification {classification_id!r} has no level {level}; "
                    f"its tree is {depth} deep",
                )
        return (
            "stringList"
            if classification.get("mode", "firstMatch") == "allMatch"
            else "string"
        )
    return None


def validate_selector(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]] | None = None,
    properties: dict[str, dict[str, Any]] | None = None,
    property_sets: dict[str, dict[str, Any]] | None = None,
    *,
    classifications: dict[str, dict[str, Any]] | None = None,
    groupings: set[str] | None = None,
    relations: set[str] | None = None,
) -> None:
    """Check a selector, and bind its concepts when the catalogs are given.

    `classifications` are the ruleset's classifications by ID, which the
    reserved set `axioval:classification` names, `groupings` the IDs of its
    groupings, which `derivedGroup` selectors and group relationships name,
    and `relations` the IDs of its relations, which relation relationships
    name; with the catalogs given and none of them, none is declared.
    """
    value = object_value(value, context)
    kind = value.get("kind")
    if type(kind) is not str:
        fail(context, "selector kind must be a string")
    if kind == "all":
        exact_keys(value, {"kind"}, set(), context)
    elif kind == "entityType":
        exact_keys(value, {"kind", "objectType", "includeSubtypes"}, set(), context)
        if (
            type(value["objectType"]) is not str
            or not QUALIFIED_ID.fullmatch(value["objectType"])
            or type(value["includeSubtypes"]) is not bool
        ):
            fail(context, "invalid entity type selector")
        if object_types is not None and value["objectType"] not in object_types:
            fail(context, "unknown object-type concept")
    elif kind == "property":
        exact_keys(
            value,
            {"kind", "property", "operator"},
            {
                "propertySet",
                "value",
                "caseSensitive",
                "trim",
                "quantifier",
                "precision",
            },
            context,
        )
        if "propertySet" in value and (
            type(value["propertySet"]) is not str
            or not QUALIFIED_ID.fullmatch(value["propertySet"])
        ):
            fail(context, "propertySet must be a qualified identifier")
        property_set = value.get("propertySet")
        reason = property_name_error(property_set, value["property"])
        if reason is not None:
            fail(context, f"invalid property selector: {reason}")
        property_kind = None
        if property_set in DERIVED_PROPERTY_SETS:
            # Derived sets name engine or ruleset vocabulary, never a concept.
            if properties is not None:
                property_kind = derived_property_kind(
                    property_set, value["property"], classifications or {}, context
                )
        else:
            if properties is not None and value["property"] not in properties:
                fail(context, "unknown property concept")
            # Reserved sets are engine vocabulary and bind to themselves; the
            # property in them is still a concept.
            if (
                property_sets is not None
                and property_set is not None
                and property_set not in RESERVED_PROPERTY_SETS
                and property_set not in property_sets
            ):
                fail(context, "unknown property-set concept")
            if properties is not None:
                property_kind = properties[value["property"]]["valueKind"]
        validate_property_comparison(value, context, property_kind)
    elif kind == "propertyPattern":
        exact_keys(
            value,
            {"kind", "propertyPattern", "matched", "operator"},
            {
                "propertySetPattern",
                "value",
                "caseSensitive",
                "trim",
                "quantifier",
                "precision",
            },
            context,
        )
        # The patterns match the source's own names: they are checked as
        # patterns and never bound through the concept catalogs.
        for key in ("propertySetPattern", "propertyPattern"):
            if key not in value:
                continue
            pattern = value[key]
            if type(pattern) is not str or not pattern:
                fail(context, f"{key} must be a non-empty string")
            error = xsd_pattern_error(pattern)
            if error is not None:
                fail(context, f"{key} is not a supported XML Schema pattern: {error}")
        if type(value["matched"]) is not str or value["matched"] not in QUANTIFIERS:
            fail(context, "matched must be 'any' or 'all'")
        # No concept names the matched properties, so their kind is unknown.
        validate_property_comparison(value, context, None)
    elif kind == "classification":
        exact_keys(
            value,
            {"kind", "system", "includeDescendants"},
            {"code", "codePattern"},
            context,
        )
        if (
            any(
                type(value[key]) is not str or not value[key]
                for key in ("system", "code", "codePattern")
                if key in value
            )
            or type(value["includeDescendants"]) is not bool
        ):
            fail(context, "invalid classification selector")
        if "code" in value and "codePattern" in value:
            fail(context, "code and codePattern exclude each other")
        if "codePattern" in value:
            error = xsd_pattern_error(value["codePattern"])
            if error is not None:
                fail(
                    context,
                    f"codePattern is not a supported XML Schema pattern: {error}",
                )
        if value["includeDescendants"] and not (
            "code" in value or "codePattern" in value
        ):
            fail(context, "includeDescendants needs code or codePattern")
    elif kind == "source":
        exact_keys(
            value,
            {"kind", "field", "operator"},
            {"value", "caseSensitive", "trim", "quantifier"},
            context,
        )
        if type(value["field"]) is not str or value["field"] not in SOURCE_FIELDS:
            fail(
                context,
                "field must be 'fileName', 'application', 'schema', 'project', "
                "or 'timestamp'",
            )
        # Source metadata is text the source states, never a concept.
        validate_property_comparison(value, context, "string")
    elif kind == "discipline":
        exact_keys(value, {"kind", "value"}, set(), context)
        if type(value["value"]) is not str or not DISCIPLINE_TOKEN.fullmatch(
            value["value"]
        ):
            fail(
                context,
                "discipline must be 1 to 64 lowercase letters, digits, '-', "
                "or '_', starting with a letter or digit",
            )
    elif kind in {"allOf", "anyOf"}:
        exact_keys(value, {"kind", "operands"}, set(), context)
        operands = list_value(value["operands"], f"{context}.operands")
        if not operands:
            fail(context, "compound selector requires operands")
        for index, operand in enumerate(operands):
            validate_selector(
                operand,
                f"{context}.operands[{index}]",
                object_types,
                properties,
                property_sets,
                classifications=classifications,
                groupings=groupings,
                relations=relations,
            )
    elif kind == "not":
        exact_keys(value, {"kind", "operand"}, set(), context)
        validate_selector(
            value["operand"],
            f"{context}.operand",
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
    elif kind == "related":
        exact_keys(value, {"kind", "path", "selector"}, {"quantifier"}, context)
        path = list_value(value["path"], f"{context}.path")
        if not path:
            fail(context, "related selector requires a path")
        for index, step in enumerate(path):
            error = path_step_error(step)
            if error is not None:
                fail(f"{context}.path[{index}]", error)
        if "quantifier" in value and (
            type(value["quantifier"]) is not str
            or value["quantifier"] not in RELATED_QUANTIFIERS
        ):
            fail(context, "quantifier must be 'any', 'all', or 'none'")
        if properties is not None:
            check_path_derived(
                path, groupings or set(), relations or set(), f"{context}.path"
            )
        validate_selector(
            value["selector"],
            f"{context}.selector",
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
    elif kind == "derivedClass":
        exact_keys(
            value, {"kind", "classification", "class"}, {"includeDescendants"}, context
        )
        if any(
            type(value[key]) is not str or not value[key].strip()
            for key in ("classification", "class")
        ):
            fail(context, "classification and class must be non-blank strings")
        if "includeDescendants" in value and value["includeDescendants"] is not True:
            fail(context, "includeDescendants is omitted unless true")
        # With the catalogs given the selector binds against the ruleset's
        # classifications, as a property in `axioval:classification` does.
        if properties is not None:
            classification = (classifications or {}).get(value["classification"])
            if classification is None:
                fail(context, f"unknown classification {value['classification']!r}")
            if value["class"] not in classification_classes(classification):
                fail(
                    context,
                    f"the classification {value['classification']!r} has no class "
                    f"{value['class']!r}",
                )
    elif kind == "derivedGroup":
        exact_keys(value, {"kind", "grouping"}, set(), context)
        if type(value["grouping"]) is not str or not value["grouping"].strip():
            fail(context, "grouping must be a non-blank string")
        # With the catalogs given the selector binds against the ruleset's
        # groupings, as a derived-class selector does against its
        # classifications.
        if properties is not None and value["grouping"] not in (groupings or set()):
            fail(context, f"unknown grouping {value['grouping']!r}")
    elif kind == "ruleOutcome":
        exact_keys(value, {"kind", "rule", "outcome"}, set(), context)
        # Whether `rule` names a rule of the same ruleset is checked once the
        # whole ruleset is known; see `validate_rule_dependencies`.
        if type(value["rule"]) is not str or not IDENTIFIER.fullmatch(value["rule"]):
            fail(context, "rule must be a rule id")
        if type(value["outcome"]) is not str or value["outcome"] not in RULE_OUTCOMES:
            fail(context, "outcome must be 'passed' or 'failed'")
    else:
        fail(context, f"unknown selector kind {kind!r}")


def selector_rule_references(value: dict[str, Any], out: set[str]) -> None:
    """Collect the rules the `ruleOutcome` selectors in a checked selector read."""
    kind = value["kind"]
    if kind == "ruleOutcome":
        out.add(value["rule"])
    elif kind in {"allOf", "anyOf"}:
        for operand in value["operands"]:
            selector_rule_references(operand, out)
    elif kind == "not":
        selector_rule_references(value["operand"], out)
    elif kind == "related":
        selector_rule_references(value["selector"], out)


def value_rule_references(value: dict[str, Any], out: set[str]) -> None:
    """Collect the rules a checked selector value or table's cells read."""
    if value["type"] == "selector":
        selector_rule_references(value["value"], out)
    elif value["type"] == "table":
        for row in value["value"]:
            for cell in row.values():
                value_rule_references(cell, out)


def validate_gate(value: Any, context: str) -> dict[str, Any]:
    """Check a rule's or folder's `gate` shape; its rule is checked later."""
    gate = object_value(value, context)
    exact_keys(gate, {"rule", "condition"}, set(), context)
    if type(gate["rule"]) is not str or not IDENTIFIER.fullmatch(gate["rule"]):
        fail(context, "rule must be a rule id")
    if (
        type(gate["condition"]) is not str
        or gate["condition"] not in GATE_CONDITIONS
    ):
        fail(
            context,
            "condition must be 'allIfPassed', 'allIfFailed', 'passedObjects', "
            "or 'failedObjects'",
        )
    return gate


def validate_rule_dependencies(
    reads: dict[str, set[str]], rule_contexts: dict[str, str]
) -> None:
    """Refuse rules reading their own outcome or reading one another in a cycle.

    `reads` maps every rule ID to the rules its gates and `ruleOutcome`
    selectors read, each already checked to be a rule of the ruleset.
    """
    for rule_id, parents in reads.items():
        if rule_id in parents:
            fail(rule_contexts[rule_id], "the rule depends on its own outcome")
    state: dict[str, int] = {}
    for start in sorted(reads):
        if state.get(start):
            continue
        # Iterative depth-first search; 1 is on the stack, 2 is finished.
        stack: list[tuple[str, list[str]]] = [(start, sorted(reads[start]))]
        state[start] = 1
        while stack:
            node, pending = stack[-1]
            if not pending:
                state[node] = 2
                stack.pop()
                continue
            parent = pending.pop()
            if state.get(parent) == 1:
                cycle = [entry for entry, _ in stack]
                cycle = cycle[cycle.index(parent) :]
                fail(
                    rule_contexts[start],
                    "the rules "
                    + ", ".join(repr(entry) for entry in cycle)
                    + " depend on one another's outcomes in a cycle",
                )
            if not state.get(parent):
                state[parent] = 1
                stack.append((parent, sorted(reads[parent])))


def validate_severity_bands(value: Any, context: str) -> None:
    """Check a rule's `severityBands`: finite, positive, strictly ascending."""
    bands = list_value(value, context)
    if not bands:
        fail(context, "severityBands is omitted when empty")
    previous = 0.0
    for index, band in enumerate(bands):
        band_context = f"{context}[{index}]"
        band = object_value(band, band_context)
        exact_keys(band, {"below", "severity"}, set(), band_context)
        below = band["below"]
        if type(below) not in {int, float} or not math.isfinite(below):
            fail(band_context, "below must be a finite number")
        if below <= previous:
            fail(
                band_context,
                f"below must lie above {previous}: thresholds are positive "
                "and strictly ascending",
            )
        previous = below
        if type(band["severity"]) is not str or band["severity"] not in SEVERITIES:
            fail(band_context, "severity must be 'info', 'warning', or 'error'")


def validate_severity_overrides(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> None:
    """Check a rule's `severityOverrides`, binding each selector's concepts."""
    overrides = list_value(value, context)
    if not overrides:
        fail(context, "severityOverrides is omitted when empty")
    for index, entry in enumerate(overrides):
        entry_context = f"{context}[{index}]"
        entry = object_value(entry, entry_context)
        exact_keys(entry, {"selector", "severity"}, set(), entry_context)
        validate_selector(
            entry["selector"],
            f"{entry_context}.selector",
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
        if type(entry["severity"]) is not str or entry["severity"] not in SEVERITIES:
            fail(entry_context, "severity must be 'info', 'warning', or 'error'")


def validate_categories(
    value: Any,
    context: str,
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> None:
    """Check a rule's `categories`: bound properties, sets, and paths."""
    levels = list_value(value, context)
    if not levels:
        fail(context, "categories is omitted when empty")
    for index, level in enumerate(levels):
        level_context = f"{context}[{index}]"
        level = object_value(level, level_context)
        exact_keys(level, {"property"}, {"propertySet", "path"}, level_context)
        property_id = level["property"]
        reason = property_name_error(level.get("propertySet"), property_id)
        if reason is not None:
            fail(level_context, reason)
        if level.get("propertySet") in DERIVED_PROPERTY_SETS:
            # Derived sets name engine or ruleset vocabulary, never a concept.
            derived_property_kind(
                level["propertySet"], property_id, classifications, level_context
            )
        elif property_id not in properties:
            fail(level_context, f"unknown property concept {property_id!r}")
        if "propertySet" in level:
            property_set = level["propertySet"]
            if type(property_set) is not str or not QUALIFIED_ID.fullmatch(
                property_set
            ):
                fail(level_context, "propertySet must be a qualified identifier")
            # Reserved sets are engine vocabulary and bind to themselves.
            if (
                property_set not in RESERVED_PROPERTY_SETS
                and property_set not in property_sets
            ):
                fail(level_context, f"unknown property-set concept {property_set!r}")
        if "path" in level:
            path = list_value(level["path"], f"{level_context}.path")
            if not path:
                fail(level_context, "path is omitted when empty")
            for step_index, step in enumerate(path):
                error = path_step_error(step)
                if error is not None:
                    fail(f"{level_context}.path[{step_index}]", error)
            check_path_derived(path, groupings, relations, f"{level_context}.path")


def validate_applicability(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> set[str]:
    value = object_value(value, context)
    if "kind" in value:
        validate_selector(
            value,
            context,
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
        return set()
    exact_keys(value, {"groups"}, set(), context)
    groups = object_value(value["groups"], f"{context}.groups")
    if not groups:
        fail(context, "rich applicability requires at least one target group")
    group_ids: set[str] = set()
    for key, group in groups.items():
        group_context = f"{context}.groups[{key!r}]"
        group = object_value(group, group_context)
        exact_keys(
            group,
            {"id", "name", "selector"},
            {"description"},
            group_context,
        )
        group_id = group["id"]
        if type(key) is not str or type(group_id) is not str:
            fail(group_context, "target-group key and id must be strings")
        if key != group_id or not IDENTIFIER.fullmatch(group_id):
            fail(group_context, "target-group map key and id must match and be valid")
        localized_text(group["name"], f"{group_context}.name")
        if "description" in group:
            localized_text(group["description"], f"{group_context}.description")
        validate_selector(
            group["selector"],
            f"{group_context}.selector",
            object_types,
            properties,
            property_sets,
            classifications=classifications,
            groupings=groupings,
            relations=relations,
        )
        group_ids.add(group_id)
    return group_ids


def selector_classification_reads(value: dict[str, Any], out: set[str]) -> None:
    """Collect the classifications the property selectors in a checked selector read."""
    kind = value["kind"]
    if kind == "property" and value.get("propertySet") == CLASSIFICATION_SET:
        out.add(value["property"].partition(";")[0])
    elif kind == "derivedClass":
        out.add(value["classification"])
    elif kind in {"allOf", "anyOf"}:
        for operand in value["operands"]:
            selector_classification_reads(operand, out)
    elif kind == "not":
        selector_classification_reads(value["operand"], out)
    elif kind == "related":
        selector_classification_reads(value["selector"], out)


def validate_classifications(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> dict[str, dict[str, Any]]:
    """Check a ruleset's `classifications` and return them by ID.

    Each is keyed by its non-blank ID and has rows of a selector bound
    against the concept catalogs and a non-blank class. Rows never read a
    rule's outcome, since classes are derived before any rule runs, nor a
    derived group, since groups are derived after the classes, and
    classifications never read one another in a cycle. A hierarchical
    classification's declared `classes` form a tree (`validate_classes`) and
    its rows assign declared classes.
    """
    classifications = object_value(value, context)
    if not classifications:
        fail(context, "classifications is omitted when empty")
    for key, classification in classifications.items():
        entry_context = f"{context}[{key!r}]"
        classification = object_value(classification, entry_context)
        exact_keys(
            classification,
            {"id", "name", "rows"},
            {"description", "mode", "classes"},
            entry_context,
        )
        if type(classification["id"]) is not str or key != classification["id"]:
            fail(entry_context, "classification map key and id must match")
        if not key.strip():
            fail(entry_context, "classification id must not be blank")
        localized_text(classification["name"], f"{entry_context}.name")
        if "description" in classification:
            localized_text(
                classification["description"], f"{entry_context}.description"
            )
        if "mode" in classification and (
            type(classification["mode"]) is not str
            or classification["mode"] not in CLASSIFICATION_MODES
        ):
            fail(entry_context, "mode must be 'firstMatch' or 'allMatch'")
        if not list_value(classification["rows"], f"{entry_context}.rows"):
            fail(entry_context, "a classification has at least one row")
        if "classes" in classification:
            validate_classes(classification, entry_context)
    reads: dict[str, set[str]] = {}
    for key, classification in classifications.items():
        read: set[str] = set()
        for index, row in enumerate(classification["rows"]):
            row_context = f"{context}[{key!r}].rows[{index}]"
            row = object_value(row, row_context)
            exact_keys(row, {"selector", "class"}, set(), row_context)
            if type(row["class"]) is not str or not row["class"].strip():
                fail(row_context, "class must be a non-blank string")
            if "classes" in classification and row["class"] not in {
                declared["id"] for declared in classification["classes"]
            }:
                fail(row_context, f"the class {row['class']!r} is not declared")
            validate_selector(
                row["selector"],
                f"{row_context}.selector",
                object_types,
                properties,
                property_sets,
                classifications=classifications,
                groupings=groupings,
                relations=relations,
            )
            rules: set[str] = set()
            selector_rule_references(row["selector"], rules)
            if rules:
                fail(
                    row_context,
                    "a row must not read a rule's outcome; classes are derived "
                    "before any rule runs",
                )
            if selector_reads_groups(row["selector"]):
                fail(
                    row_context,
                    "a row must not read a derived group; groups are derived "
                    "after the classes",
                )
            selector_classification_reads(row["selector"], read)
        reads[key] = read
    pending = set(reads)
    while pending:
        ready = sorted(
            key for key in pending if not any(needed in pending for needed in reads[key])
        )
        if not ready:
            fail(
                context,
                "the classifications "
                + ", ".join(repr(key) for key in sorted(pending))
                + " read one another in a cycle",
            )
        pending -= set(ready)
    return classifications


def selector_reads_groups(value: dict[str, Any]) -> bool:
    """Whether a checked selector reads derived groups: a `derivedGroup`
    selector or a property of the reserved set `axioval:group`."""
    kind = value["kind"]
    if kind == "derivedGroup":
        return True
    if kind == "property":
        return value.get("propertySet") == GROUP_SET
    if kind in {"allOf", "anyOf"}:
        return any(selector_reads_groups(operand) for operand in value["operands"])
    if kind == "not":
        return selector_reads_groups(value["operand"])
    if kind == "related":
        return selector_reads_groups(value["selector"])
    return False


def validate_grouping_selector(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> None:
    """Check a selector of a grouping, bound against the concept catalogs.

    Groups are derived from the model alone before any rule runs, so the
    selector reads neither a rule's outcome nor a derived group.
    """
    validate_selector(
        value,
        context,
        object_types,
        properties,
        property_sets,
        classifications=classifications,
        groupings=groupings,
        relations=relations,
    )
    rules: set[str] = set()
    selector_rule_references(value, rules)
    if rules:
        fail(
            context,
            "a grouping must not read a rule's outcome; groups are derived "
            "before any rule runs",
        )
    if selector_reads_groups(value):
        fail(
            context,
            "a grouping must not read a derived group; groups are derived "
            "from the model alone",
        )


def bind_key_property(
    value: dict[str, Any],
    context: str,
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
) -> None:
    """Bind the property a grouping or relation key reads: a property concept,
    in an optional declared or reserved set, or a name in a derived set."""
    property_set = value.get("propertySet")
    if "propertySet" in value and (
        type(property_set) is not str or not QUALIFIED_ID.fullmatch(property_set)
    ):
        fail(context, "propertySet must be a qualified identifier")
    reason = property_name_error(property_set, value["property"])
    if reason is not None:
        fail(context, reason)
    if property_set in DERIVED_PROPERTY_SETS:
        # Derived sets name engine or ruleset vocabulary, never a concept.
        derived_property_kind(property_set, value["property"], classifications, context)
    else:
        if value["property"] not in properties:
            fail(context, f"unknown property concept {value['property']!r}")
        # Reserved sets are engine vocabulary and bind to themselves.
        if (
            property_set is not None
            and property_set not in RESERVED_PROPERTY_SETS
            and property_set not in property_sets
        ):
            fail(context, f"unknown property-set concept {property_set!r}")


def validate_grouping_key(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    relations: set[str],
) -> None:
    """Check what a grouping groups its members `by`, tagged by `kind`.

    - `property`: equal values of one bound property, never one of the
      reserved set `axioval:group`.
    - `classification`: equal codes in the non-blank classification `system`
      the source states.
    - `compartment`: connected regions of members not separated by an
      element `boundary` selects, joined across `separators`; the optional
      `tolerance` is a finite number of at least zero, `overlap` a finite
      positive one.
    """
    value = object_value(value, context)
    kind = value.get("kind")
    if type(kind) is not str or kind not in GROUPING_KINDS:
        fail(context, "kind must be 'property', 'classification', or 'compartment'")
    if kind == "property":
        exact_keys(value, {"kind", "property"}, {"propertySet"}, context)
        if value.get("propertySet") == GROUP_SET:
            fail(context, "a grouping must not group by a derived group's own facts")
        bind_key_property(value, context, properties, property_sets, classifications)
    elif kind == "classification":
        exact_keys(value, {"kind", "system"}, set(), context)
        if type(value["system"]) is not str or not value["system"].strip():
            fail(context, "system must be a non-blank string")
    else:
        exact_keys(
            value, {"kind", "separators", "boundary"}, {"tolerance", "overlap"}, context
        )
        for key, positive in (("tolerance", False), ("overlap", True)):
            if key not in value:
                continue
            number = value[key]
            if (
                type(number) not in {int, float}
                or not math.isfinite(number)
                or number < 0
                or (positive and number == 0)
            ):
                fail(
                    context,
                    f"{key} must be a finite number "
                    + ("greater than zero" if positive else "of at least zero"),
                )
        for key in ("separators", "boundary"):
            validate_grouping_selector(
                value[key],
                f"{context}.{key}",
                object_types,
                properties,
                property_sets,
                classifications,
                groupings,
                relations,
            )


def validate_groupings(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    relations: set[str],
) -> set[str]:
    """Check a ruleset's `groupings` and return their IDs.

    Each is keyed by its ID, which is not blank and holds no `:`, `;`, `|`,
    `/` or whitespace, since it is part of every group's identity. Its
    `members` selector and what it groups them `by` bind against the concept
    catalogs and the ruleset's classifications, and read neither a rule's
    outcome nor a derived group.
    """
    groupings = object_value(value, context)
    if not groupings:
        fail(context, "groupings is omitted when empty")
    declared = set(groupings)
    for key, grouping in groupings.items():
        entry_context = f"{context}[{key!r}]"
        grouping = object_value(grouping, entry_context)
        exact_keys(
            grouping, {"id", "name", "members", "by"}, {"description"}, entry_context
        )
        if type(grouping["id"]) is not str or key != grouping["id"]:
            fail(entry_context, "grouping map key and id must match")
        if not GROUPING_ID.fullmatch(key):
            fail(
                entry_context,
                "a grouping id must not be blank or hold ':', ';', '|', '/' or "
                "whitespace",
            )
        localized_text(grouping["name"], f"{entry_context}.name")
        if "description" in grouping:
            localized_text(grouping["description"], f"{entry_context}.description")
        validate_grouping_selector(
            grouping["members"],
            f"{entry_context}.members",
            object_types,
            properties,
            property_sets,
            classifications,
            declared,
            relations,
        )
        validate_grouping_key(
            grouping["by"],
            f"{entry_context}.by",
            object_types,
            properties,
            property_sets,
            classifications,
            declared,
            relations,
        )
    return declared


def selector_reads_relations(value: dict[str, Any]) -> bool:
    """Whether a checked selector walks a declared relation: a related
    selector with a path step naming `axioval:derived.relation;id=`."""
    kind = value["kind"]
    if kind == "related":
        return any(
            RELATION_RELATIONSHIP_PREFIX in step for step in value["path"]
        ) or selector_reads_relations(value["selector"])
    if kind in {"allOf", "anyOf"}:
        return any(selector_reads_relations(operand) for operand in value["operands"])
    if kind == "not":
        return selector_reads_relations(value["operand"])
    return False


def relation_pairs(
    value: Any, context: str, asset_root: Path | None
) -> None:
    """Check a relation's listed `pairs`: a `table` or `tableFile` value
    whose rows hold the required text cells `from` and `to`, neither blank."""
    value = object_value(value, context)
    kind = value.get("type")
    if kind == "table":
        exact_keys(value, {"type", "value"}, set(), context)
        table_rows(value, RELATION_PAIR_COLUMNS, context)
        rows = value["value"]
    elif kind == TABLE_FILE:
        table_file_reference(value, context)
        rows = bind_table_file(value, RELATION_PAIR_COLUMNS, context, asset_root)
    else:
        fail(context, "pairs must be a table or a table file")
    for index, row in enumerate(rows):
        if any(not cell["value"].strip(TRIMMED) for cell in row.values()):
            fail(context, f"pairs row {index + 1} names a blank object")


def supplied_columns(value: Any, context: str) -> None:
    """Check the `columns` a supplied relation's pairs are taken by, as the
    engine checks them: exactly the text columns `from` and `to`, each once,
    with distinct non-empty headers. Omitted, the headers are `from` and
    `to`."""
    columns = list_value(value, f"{context}.columns")
    table_file_columns(columns, context)
    for index, column in enumerate(columns):
        if column["id"] not in {"from", "to"}:
            fail(
                f"{context}.columns[{index}]",
                f"supplied column {column['id']!r} is neither 'from' nor 'to'",
            )
        if column["kind"] != "string":
            fail(
                f"{context}.columns[{index}]",
                f"supplied column {column['id']!r} is declared {column['kind']}, "
                "not string",
            )
    for missing in ("from", "to"):
        if not any(column["id"] == missing for column in columns):
            fail(context, f"the supplied columns declare no {missing!r}")


def validate_relations(
    value: Any,
    context: str,
    object_types: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    property_sets: dict[str, dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    groupings: set[str],
    asset_root: Path | None,
) -> set[str]:
    """Check a ruleset's `relations` and return their IDs.

    Each is keyed by its ID, which is not blank and holds no `:`, `;`, `|`,
    `/` or whitespace, since it is part of every pair's identity. Its `from`
    and `to` selectors bind against the concept catalogs, the ruleset's
    classifications and groupings, and read neither a rule's outcome nor a
    declared relation, since relations are derived before any rule runs. It
    relates `by` equal values of two bound properties, or by listed `pairs`
    of objects named by their identity or, with a non-blank `scheme`, by
    their external ID in that scheme, or by pairs the host supplies at check
    time (`supplied`, with optional `from` and `to` `columns`), which the
    package never states.
    """
    relations = object_value(value, context)
    if not relations:
        fail(context, "relations is omitted when empty")
    declared = set(relations)
    for key, relation in relations.items():
        entry_context = f"{context}[{key!r}]"
        relation = object_value(relation, entry_context)
        exact_keys(
            relation, {"id", "name", "from", "to", "by"}, {"description"}, entry_context
        )
        if type(relation["id"]) is not str or key != relation["id"]:
            fail(entry_context, "relation map key and id must match")
        if not RELATION_ID.fullmatch(key):
            fail(
                entry_context,
                "a relation id must not be blank or hold ':', ';', '|', '/' or "
                "whitespace",
            )
        localized_text(relation["name"], f"{entry_context}.name")
        if "description" in relation:
            localized_text(relation["description"], f"{entry_context}.description")
        for end in ("from", "to"):
            end_context = f"{entry_context}.{end}"
            validate_selector(
                relation[end],
                end_context,
                object_types,
                properties,
                property_sets,
                classifications=classifications,
                groupings=groupings,
                relations=declared,
            )
            rules: set[str] = set()
            selector_rule_references(relation[end], rules)
            if rules or selector_reads_relations(relation[end]):
                fail(
                    end_context,
                    "a relation must not read a rule's outcome or a declared "
                    "relation; relations are derived before any rule runs",
                )
        by_context = f"{entry_context}.by"
        by = object_value(relation["by"], by_context)
        kind = by.get("kind")
        if type(kind) is not str or kind not in RELATION_KINDS:
            fail(by_context, "kind must be 'property', 'pairs' or 'supplied'")
        if kind == "property":
            exact_keys(by, {"kind", "from", "to"}, set(), by_context)
            for end in ("from", "to"):
                end_context = f"{by_context}.{end}"
                key_property = object_value(by[end], end_context)
                exact_keys(key_property, {"property"}, {"propertySet"}, end_context)
                bind_key_property(
                    key_property, end_context, properties, property_sets, classifications
                )
        else:
            if kind == "pairs":
                exact_keys(by, {"kind", "pairs"}, {"scheme"}, by_context)
            else:
                exact_keys(by, {"kind"}, {"columns", "scheme"}, by_context)
            if "scheme" in by and (
                type(by["scheme"]) is not str or not by["scheme"].strip(TRIMMED)
            ):
                fail(by_context, "the external id scheme must be a non-blank string")
            if kind == "pairs":
                relation_pairs(by["pairs"], f"{by_context}.pairs", asset_root)
            elif "columns" in by:
                supplied_columns(by["columns"], by_context)
    return declared


def validate_parameter_citations(
    value: Any,
    bound_parameter_ids: set[str],
    sources: dict[str, dict[str, Any]],
    context: str,
    citation_ids: set[str],
) -> None:
    for index, candidate in enumerate(list_value(value, context)):
        entry_context = f"{context}[{index}]"
        entry = object_value(candidate, entry_context)
        exact_keys(entry, {"parameterIds", "citation"}, set(), entry_context)
        parameter_ids = string_list(
            entry["parameterIds"], f"{entry_context}.parameterIds"
        )
        if not parameter_ids or len(parameter_ids) != len(set(parameter_ids)):
            fail(entry_context, "parameterIds must be non-empty and unique")
        invalid = {
            parameter_id
            for parameter_id in parameter_ids
            if not IDENTIFIER.fullmatch(parameter_id)
            or parameter_id not in bound_parameter_ids
        }
        if invalid:
            fail(entry_context, f"unknown bound parameters {sorted(invalid)}")
        validate_citations(
            [entry["citation"]],
            sources,
            f"{entry_context}.citation",
            citation_ids,
        )


def validate_requirements(
    value: Any,
    target_groups: set[str],
    sources: dict[str, dict[str, Any]],
    context: str,
    citation_ids: set[str],
) -> None:
    requirements = list_value(value, context)
    if requirements and not target_groups:
        fail(context, "requirements require rich applicability target groups")
    seen_ids: set[str] = set()
    for index, requirement in enumerate(requirements):
        requirement_context = f"{context}[{index}]"
        requirement = object_value(requirement, requirement_context)
        exact_keys(
            requirement,
            {"id", "statement", "targetGroups"},
            {"description", "citations"},
            requirement_context,
        )
        requirement_id = requirement["id"]
        if type(requirement_id) is not str or not IDENTIFIER.fullmatch(requirement_id):
            fail(requirement_context, "invalid requirement id")
        if requirement_id in seen_ids:
            fail(requirement_context, f"duplicate requirement id {requirement_id!r}")
        seen_ids.add(requirement_id)
        localized_text(requirement["statement"], f"{requirement_context}.statement")
        if "description" in requirement:
            localized_text(
                requirement["description"], f"{requirement_context}.description"
            )
        referenced = string_list(
            requirement["targetGroups"], f"{requirement_context}.targetGroups"
        )
        if not referenced or len(set(referenced)) != len(referenced):
            fail(requirement_context, "targetGroups must be non-empty and unique")
        invalid = {
            group_id
            for group_id in referenced
            if not IDENTIFIER.fullmatch(group_id) or group_id not in target_groups
        }
        if invalid:
            fail(requirement_context, f"unknown target groups {sorted(invalid)}")
        validate_citations(
            requirement.get("citations", []),
            sources,
            f"{requirement_context}.citations",
            citation_ids,
        )


def validate_image_content(candidate: Path, media_type: str, context: str) -> None:
    if candidate.stat().st_size > 10_000_000:
        fail(context, "package image exceeds the 10 MB safety limit")
    content = candidate.read_bytes()
    if media_type == "image/svg+xml":
        if b"<!DOCTYPE" in content.upper():
            fail(context, "SVG must not contain a document type")
        blocked_elements = {
            "a",
            "animate",
            "animatemotion",
            "animatetransform",
            "embed",
            "foreignobject",
            "iframe",
            "object",
            "script",
            "set",
            "style",
        }
        root_name: str | None = None

        def local_name(name: str) -> str:
            return name.rsplit("}", 1)[-1].lower()

        def reject_declaration(*_args: Any) -> None:
            raise ValueError("active SVG declaration")

        def start_element(name: str, attributes: dict[str, str]) -> None:
            nonlocal root_name
            element_name = local_name(name)
            if root_name is None:
                root_name = element_name
            if element_name in blocked_elements:
                raise ValueError("active SVG element")
            for raw_attribute, raw_value in attributes.items():
                attribute = local_name(raw_attribute)
                value = raw_value.strip().lower()
                if attribute.startswith("on") or attribute in {"base", "style"}:
                    raise ValueError("active SVG attribute")
                if attribute == "href" and value and not value.startswith("#"):
                    raise ValueError("external SVG reference")
                if (
                    "url(" in value
                    and re.fullmatch(r"url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)", value)
                    is None
                ):
                    raise ValueError("external SVG URL")
                if any(
                    token in value
                    for token in (
                        "data:",
                        "javascript:",
                        "http://",
                        "https://",
                        "//",
                    )
                ):
                    raise ValueError("external or executable SVG value")

        parser = expat.ParserCreate(namespace_separator="}")
        parser.StartElementHandler = start_element
        parser.StartDoctypeDeclHandler = reject_declaration
        parser.EntityDeclHandler = reject_declaration
        parser.ProcessingInstructionHandler = reject_declaration
        parser.ExternalEntityRefHandler = reject_declaration
        try:
            parser.Parse(content, True)
        except ValueError:
            fail(context, "SVG contains active or foreign content")
        except expat.ExpatError:
            fail(context, "SVG is not well-formed XML")
        if root_name != "svg":
            fail(context, "SVG document has the wrong root element")
        return
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP",
    }
    if not signatures.get(media_type, False):
        fail(context, "image bytes do not match the declared media type")


def validate_explanatory_images(
    value: Any, context: str, asset_root: Path | None
) -> None:
    images = list_value(value, context)
    if images and asset_root is None:
        fail(context, "package asset root is required for explanatory images")
    seen_ids: set[str] = set()
    resolved_root = asset_root.resolve() if asset_root is not None else None
    for index, image in enumerate(images):
        image_context = f"{context}[{index}]"
        image = object_value(image, image_context)
        exact_keys(
            image,
            {"id", "path", "mediaType", "alternativeText"},
            {"caption"},
            image_context,
        )
        image_id = image["id"]
        if type(image_id) is not str or not IDENTIFIER.fullmatch(image_id):
            fail(image_context, "invalid explanatory-image id")
        if image_id in seen_ids:
            fail(image_context, f"duplicate explanatory-image id {image_id!r}")
        seen_ids.add(image_id)
        path = image["path"]
        media_type = image["mediaType"]
        if type(path) is not str or type(media_type) is not str or "\\" in path:
            fail(image_context, "image path and mediaType must be strings")
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.as_posix() != path
        ):
            fail(image_context, "image path must be a normalized relative path")
        expected_media_type = IMAGE_MEDIA_TYPES.get(relative.suffix.lower())
        if expected_media_type is None or media_type != expected_media_type:
            fail(image_context, "image extension and mediaType do not match")
        localized_text(image["alternativeText"], f"{image_context}.alternativeText")
        if "caption" in image:
            localized_text(image["caption"], f"{image_context}.caption")
        if resolved_root is not None:
            candidate = (resolved_root / path).resolve()
            if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
                fail(
                    image_context,
                    "referenced package image is missing or escapes package",
                )
            validate_image_content(candidate, media_type, image_context)


def bind_ruleset(
    value: Any,
    definition_documents: list[dict[str, Any]],
    context: str,
    *,
    asset_root: Path | None = None,
) -> None:
    value = object_value(value, context)
    exact_keys(
        value,
        {"schemaVersion", "package", "sources", "definitionPackages", "root"},
        {"classifications", "groupings", "relations"},
        context,
    )
    package_metadata(value["package"], f"{context}.package")
    sources = validate_sources(value["sources"], f"{context}.sources")
    declared_list = string_list(
        value["definitionPackages"], f"{context}.definitionPackages"
    )
    if (
        not declared_list
        or any(not QUALIFIED_ID.fullmatch(package_id) for package_id in declared_list)
        or len(set(declared_list)) != len(declared_list)
    ):
        fail(context, "definitionPackages must be non-empty, qualified, and unique")
    definitions: dict[str, dict[str, Any]] = {}
    object_types: dict[str, dict[str, Any]] = {}
    properties: dict[str, dict[str, Any]] = {}
    property_sets: dict[str, dict[str, Any]] = {}
    loaded_packages: set[str] = set()
    for index, document in enumerate(definition_documents):
        (
            package_id,
            package_definitions,
            package_object_types,
            package_properties,
            package_property_sets,
        ) = validate_definition_document(
            document, f"{context}.definitionDocuments[{index}]", asset_root=asset_root
        )
        if package_id in loaded_packages:
            fail(context, f"duplicate definition package {package_id!r}")
        loaded_packages.add(package_id)
        overlap = definitions.keys() & package_definitions.keys()
        if overlap:
            fail(context, f"duplicate definition ids {sorted(overlap)}")
        definitions.update(package_definitions)
        object_type_overlap = object_types.keys() & package_object_types.keys()
        if object_type_overlap:
            fail(
                context, f"duplicate object-type concepts {sorted(object_type_overlap)}"
            )
        object_types.update(package_object_types)
        property_overlap = properties.keys() & package_properties.keys()
        property_set_overlap = property_sets.keys() & package_property_sets.keys()
        if property_overlap or property_set_overlap:
            fail(
                context,
                "duplicate property concepts "
                f"{sorted(property_overlap | property_set_overlap)}",
            )
        properties.update(package_properties)
        property_sets.update(package_property_sets)
    component_kinds: dict[str, str] = {}
    for kind, components in (
        ("rule definition", definitions),
        ("object type", object_types),
        ("property", properties),
        ("property set", property_sets),
    ):
        for component_id in components:
            if component_id in component_kinds:
                fail(
                    context,
                    f"component id {component_id!r} is both {component_kinds[component_id]} and {kind}",
                )
            component_kinds[component_id] = kind
    # The groupings' IDs, which classification rows may not read and every
    # other selector binds against; the groupings themselves are checked once
    # the classifications their selectors may read are.
    groupings: set[str] = set()
    if "groupings" in value:
        groupings = set(object_value(value["groupings"], f"{context}.groupings"))
    # The relations' IDs, which every selector's path binds against; the
    # relations themselves are checked once the classifications and groupings
    # their selectors may read are.
    relations: set[str] = set()
    if "relations" in value:
        relations = set(object_value(value["relations"], f"{context}.relations"))
    classifications: dict[str, dict[str, Any]] = {}
    if "classifications" in value:
        classifications = validate_classifications(
            value["classifications"],
            f"{context}.classifications",
            object_types,
            properties,
            property_sets,
            groupings,
            relations,
        )
    if "groupings" in value:
        validate_groupings(
            value["groupings"],
            f"{context}.groupings",
            object_types,
            properties,
            property_sets,
            classifications,
            relations,
        )
    if "relations" in value:
        validate_relations(
            value["relations"],
            f"{context}.relations",
            object_types,
            properties,
            property_sets,
            classifications,
            groupings,
            asset_root,
        )
    for definition_id, definition in definitions.items():
        for parameter_id, parameter in definition["parameters"].items():
            for field in ("defaultValue",):
                if field in parameter:
                    candidate = parameter[field]
                    value_context = f"{context}.definitions[{definition_id!r}].parameters[{parameter_id!r}].{field}"
                    resolve_selector_value(
                        candidate,
                        object_types,
                        properties,
                        property_sets,
                        value_context,
                        classifications,
                        groupings,
                        relations,
                    )
                    resolve_object_type_reference(
                        candidate, object_types, value_context
                    )
                    resolve_property_reference(
                        candidate,
                        properties,
                        property_sets,
                        value_context,
                        parameter.get("referencedValueKind"),
                        classifications,
                    )
            for index, allowed in enumerate(parameter["allowedValues"]):
                allowed_context = f"{context}.definitions[{definition_id!r}].parameters[{parameter_id!r}].allowedValues[{index}]"
                resolve_selector_value(
                    allowed,
                    object_types,
                    properties,
                    property_sets,
                    allowed_context,
                    classifications,
                    groupings,
                    relations,
                )
                resolve_object_type_reference(allowed, object_types, allowed_context)
                resolve_property_reference(
                    allowed,
                    properties,
                    property_sets,
                    allowed_context,
                    parameter.get("referencedValueKind"),
                    classifications,
                )
    if set(declared_list) != loaded_packages:
        fail(
            context,
            f"declared definition packages {sorted(declared_list)} do not match loaded packages {sorted(loaded_packages)}",
        )
    seen_ids: set[str] = set()
    # The rules each rule's gates and rule-outcome selectors read, checked
    # once every rule of the ruleset is known.
    reads: dict[str, set[str]] = {}
    rule_contexts: dict[str, str] = {}
    # The enabled rules, and those of them that are auxiliary.
    enabled: set[str] = set()
    auxiliary: set[str] = set()

    def walk(folder: Any, folder_context: str, inherited: tuple[str, ...]) -> set[str]:
        """Check `folder` and return the IDs of the rules in it and below."""
        folder = object_value(folder, folder_context)
        exact_keys(
            folder,
            {"id", "name", "rules", "folders"},
            {"description", "gate", "annotations"},
            folder_context,
        )
        folder_id = folder["id"]
        if type(folder_id) is not str or not IDENTIFIER.fullmatch(folder_id):
            fail(folder_context, "invalid folder id")
        if folder_id in seen_ids:
            fail(folder_context, f"duplicate rule/folder id {folder_id!r}")
        seen_ids.add(folder_id)
        localized_text(folder["name"], f"{folder_context}.name")
        if "description" in folder:
            localized_text(folder["description"], f"{folder_context}.description")
        if "annotations" in folder:
            annotations = object_value(
                folder["annotations"], f"{folder_context}.annotations"
            )
            if not annotations:
                fail(folder_context, "empty annotations are omitted, not written")
            for key, text in annotations.items():
                if not QUALIFIED_ID.fullmatch(key):
                    fail(folder_context, f"annotation key {key!r} is not scheme:name")
                if type(text) is not str:
                    fail(folder_context, f"annotation {key!r} is not text")
        folder_gate = None
        if "gate" in folder:
            folder_gate = validate_gate(folder["gate"], f"{folder_context}.gate")
            inherited = (*inherited, folder_gate["rule"])
        subtree: set[str] = set()
        for index, rule in enumerate(
            list_value(folder["rules"], f"{folder_context}.rules")
        ):
            rule_context = f"{folder_context}.rules[{index}]"
            rule = object_value(rule, rule_context)
            exact_keys(
                rule,
                {
                    "id",
                    "definitionId",
                    "name",
                    "enabled",
                    "severity",
                    "parameters",
                    "applicability",
                    "tags",
                },
                {
                    "description",
                    "message",
                    "requirements",
                    "citations",
                    "parameterCitations",
                    "explanatoryImages",
                    "severityBands",
                    "severityOverrides",
                    "categories",
                    "gate",
                    "auxiliary",
                },
                rule_context,
            )
            rule_id = rule["id"]
            definition_id = rule["definitionId"]
            if type(rule_id) is not str or not IDENTIFIER.fullmatch(rule_id):
                fail(rule_context, "invalid rule id")
            if type(definition_id) is not str or not QUALIFIED_ID.fullmatch(
                definition_id
            ):
                fail(rule_context, "invalid definitionId")
            if (
                type(rule["enabled"]) is not bool
                or type(rule["severity"]) is not str
                or rule["severity"] not in SEVERITIES
            ):
                fail(rule_context, "invalid enabled flag or severity")
            # Normalized JSON omits a false `auxiliary`.
            if "auxiliary" in rule and rule["auxiliary"] is not True:
                fail(rule_context, "auxiliary is true or omitted")
            if rule["enabled"]:
                enabled.add(rule_id)
                if rule.get("auxiliary", False):
                    auxiliary.add(rule_id)
            localized_text(rule["name"], f"{rule_context}.name")
            for field in ("description", "message"):
                if field in rule:
                    localized_text(rule[field], f"{rule_context}.{field}")
            string_list(rule["tags"], f"{rule_context}.tags")
            if rule_id in seen_ids:
                fail(rule_context, f"duplicate rule/folder id {rule_id!r}")
            seen_ids.add(rule_id)
            definition = definitions.get(definition_id)
            if definition is None:
                fail(rule_context, f"unknown definitionId {definition_id!r}")
            bindings = object_value(rule["parameters"], f"{rule_context}.parameters")
            parameters = definition["parameters"]
            unknown = bindings.keys() - parameters.keys()
            missing = {
                key for key, parameter in parameters.items() if parameter["required"]
            } - bindings.keys()
            if unknown or missing:
                fail(
                    rule_context,
                    f"unknown parameters={sorted(unknown)}, missing required parameters={sorted(missing)}",
                )
            for parameter_id, binding in bindings.items():
                parameter = parameters[parameter_id]
                checked = parameter_value(
                    binding,
                    parameter["kind"],
                    f"{rule_context}.parameters[{parameter_id!r}]",
                    parameter.get("columns"),
                    asset_root,
                )
                resolve_selector_value(
                    checked,
                    object_types,
                    properties,
                    property_sets,
                    f"{rule_context}.parameters[{parameter_id!r}].value",
                    classifications,
                    groupings,
                    relations,
                )
                resolve_object_type_reference(
                    checked,
                    object_types,
                    f"{rule_context}.parameters[{parameter_id!r}]",
                )
                resolve_property_reference(
                    checked,
                    properties,
                    property_sets,
                    f"{rule_context}.parameters[{parameter_id!r}]",
                    parameter.get("referencedValueKind"),
                    classifications,
                )
                if (
                    parameter["allowedValues"]
                    and checked not in parameter["allowedValues"]
                ):
                    fail(
                        rule_context,
                        f"parameter {parameter_id!r} is outside allowedValues",
                    )
            citation_ids: set[str] = set()
            validate_citations(
                rule.get("citations", []),
                sources,
                f"{rule_context}.citations",
                citation_ids,
            )
            validate_parameter_citations(
                rule.get("parameterCitations", []),
                set(bindings),
                sources,
                f"{rule_context}.parameterCitations",
                citation_ids,
            )
            target_groups = validate_applicability(
                rule["applicability"],
                f"{rule_context}.applicability",
                object_types,
                properties,
                property_sets,
                classifications,
                groupings,
                relations,
            )
            validate_requirements(
                rule.get("requirements", []),
                target_groups,
                sources,
                f"{rule_context}.requirements",
                citation_ids,
            )
            validate_explanatory_images(
                rule.get("explanatoryImages", []),
                f"{rule_context}.explanatoryImages",
                asset_root,
            )
            if "severityBands" in rule:
                validate_severity_bands(
                    rule["severityBands"], f"{rule_context}.severityBands"
                )
            if "severityOverrides" in rule:
                validate_severity_overrides(
                    rule["severityOverrides"],
                    f"{rule_context}.severityOverrides",
                    object_types,
                    properties,
                    property_sets,
                    classifications,
                    groupings,
                    relations,
                )
            if "categories" in rule:
                validate_categories(
                    rule["categories"],
                    f"{rule_context}.categories",
                    properties,
                    property_sets,
                    classifications,
                    groupings,
                    relations,
                )
            # Every rule this one reads: its folders' gates and its own, and
            # the rule-outcome selectors of its applicability, parameters
            # (bound or defaulted), and severity overrides.
            read = set(inherited)
            if "gate" in rule:
                read.add(validate_gate(rule["gate"], f"{rule_context}.gate")["rule"])
            applicability = rule["applicability"]
            if "kind" in applicability:
                selector_rule_references(applicability, read)
            else:
                for group in applicability["groups"].values():
                    selector_rule_references(group["selector"], read)
            for parameter_id, parameter in parameters.items():
                effective = bindings.get(parameter_id, parameter.get("defaultValue"))
                if effective is not None:
                    value_rule_references(effective, read)
            for entry in rule.get("severityOverrides", []):
                selector_rule_references(entry["selector"], read)
            reads[rule_id] = read
            rule_contexts[rule_id] = rule_context
            subtree.add(rule_id)
        for index, child in enumerate(
            list_value(folder["folders"], f"{folder_context}.folders")
        ):
            subtree |= walk(child, f"{folder_context}.folders[{index}]", inherited)
        if folder_gate is not None and folder_gate["rule"] in subtree:
            fail(
                f"{folder_context}.gate",
                f"a folder's gate must name a rule outside the folder, not "
                f"{folder_gate['rule']!r}",
            )
        return subtree

    walk(value["root"], f"{context}.root", ())
    for rule_id, read in reads.items():
        unknown = sorted(read - reads.keys())
        if unknown:
            fail(
                rule_contexts[rule_id],
                f"the rule depends on rules {unknown}, which the ruleset does "
                "not define",
            )
    validate_rule_dependencies(reads, rule_contexts)
    # An auxiliary rule reports only through the rules that read it, so one
    # no enabled rule reads would never reach the report.
    for rule_id in sorted(auxiliary):
        if not any(rule_id in reads[reader] for reader in enabled):
            fail(
                rule_contexts[rule_id],
                "the rule is auxiliary, but no enabled rule reads its outcome "
                "through a gate or a ruleOutcome selector",
            )
