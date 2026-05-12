from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class FieldMapping:
    id: str
    collection: str
    field: str
    cn_name: str
    type: str
    description: str
    section: str
    search_text: str


HEADER_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
BACKTICK_RE = re.compile(r"^`(.+)`$")


def parse_data_dictionary(path: Path | str) -> list[FieldMapping]:
    text = Path(path).read_text(encoding="utf-8")
    collection = ""
    section = ""
    mappings: list[FieldMapping] = []
    table: list[str] = []

    for line in text.splitlines() + [""]:
        header = HEADER_RE.match(line)
        if header:
            mappings.extend(_parse_table(table, collection, section))
            table = []
            level, title = header.groups()
            if level == "##":
                collection = title.split("（", 1)[0].strip()
                section = collection
            else:
                section = title.strip()
            continue

        if line.strip().startswith("|"):
            table.append(line)
            continue

        if table:
            mappings.extend(_parse_table(table, collection, section))
            table = []

    return mappings


def mapping_lookup(mappings: list[FieldMapping]) -> dict[str, FieldMapping]:
    return {item.id: item for item in mappings}


def collection_fields(mappings: list[FieldMapping]) -> dict[str, dict[str, FieldMapping]]:
    collections: dict[str, dict[str, FieldMapping]] = {}
    for item in mappings:
        collections.setdefault(item.collection, {})[item.field] = item
    return collections


def _parse_table(lines: list[str], collection: str, section: str) -> list[FieldMapping]:
    if not collection or len(lines) < 2:
        return []

    header = [_clean_cell(cell) for cell in _split_row(lines[0])]
    indexes = {name: i for i, name in enumerate(header)}
    if "字段名" not in indexes or "中文名" not in indexes:
        return []

    items: list[FieldMapping] = []
    for line in lines[2:]:
        cells = [_clean_cell(cell) for cell in _split_row(line)]
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        field = _unquote(cells[indexes["字段名"]])
        cn_name = cells[indexes["中文名"]]
        if not field or set(field) <= {"-", " "}:
            continue
        field_type = _normalize_field_type(field, cells[indexes["类型"]] if "类型" in indexes else "")
        description = _normalize_description(field, cells[indexes["说明"]] if "说明" in indexes else "")
        search_text = (
            f"ETF字段 {cn_name} {description} 所属分组:{section} "
            f"集合:{collection} 字段:{field}"
        )
        items.append(
            FieldMapping(
                id=f"{collection}.{field}",
                collection=collection,
                field=field,
                cn_name=cn_name,
                type=field_type,
                description=description,
                section=section,
                search_text=search_text,
            )
        )
    return items


def _split_row(line: str) -> list[str]:
    return line.strip().strip("|").split("|")


def _clean_cell(cell: str) -> str:
    return cell.strip().replace("\\|", "|")


def _unquote(value: str) -> str:
    match = BACKTICK_RE.match(value)
    return match.group(1) if match else value


def _normalize_field_type(field: str, field_type: str) -> str:
    if field == "ths_fund_scale_fund":
        return "number"
    return field_type


def _normalize_description(field: str, description: str) -> str:
    if field == "ths_fund_scale_fund":
        return "单位：元"
    return description
