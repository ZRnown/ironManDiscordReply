import csv
import os
import re
import zipfile
from typing import Dict, List, Sequence, TypeVar
from xml.etree import ElementTree as ET

T = TypeVar("T")
FlagT = TypeVar("FlagT")

EXCEL_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXCEL_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def split_keywords(text: str) -> List[str]:
    return [keyword.strip() for keyword in re.split(r"[,\n，;；]+", text) if keyword.strip()]


def parse_channel_ids(text: str) -> List[int]:
    channel_text = text.strip()
    if not channel_text:
        return []

    channel_ids = []
    seen_channel_ids = set()

    for segment in re.split(r"[,，;；\s]+", channel_text):
        cleaned_segment = segment.strip()
        if not cleaned_segment:
            continue
        if not cleaned_segment.isdigit():
            raise ValueError(f"频道ID只能填数字，发现无效内容：{cleaned_segment}")

        channel_id = int(cleaned_segment)
        if channel_id in seen_channel_ids:
            continue
        channel_ids.append(channel_id)
        seen_channel_ids.add(channel_id)

    return channel_ids


def parse_rule_import_file(filepath: str) -> tuple[List[Dict[str, object]], int]:
    extension = os.path.splitext(filepath)[1].lower()
    if extension == ".csv":
        rows = _load_csv_rows(filepath)
    elif extension == ".xlsx":
        rows = _load_xlsx_rows(filepath)
    else:
        raise ValueError("仅支持 .xlsx 或 .csv 文件")

    if rows and _looks_like_rule_header(rows[0]):
        rows = rows[1:]

    imported_rules = []
    skipped_rows = 0

    for row in rows:
        keyword_text = row[0].strip() if len(row) > 0 else ""
        reply_text = row[1].strip() if len(row) > 1 else ""

        if not keyword_text and not reply_text:
            continue
        if not keyword_text or not reply_text:
            skipped_rows += 1
            continue

        keywords = split_keywords(keyword_text)
        if not keywords:
            skipped_rows += 1
            continue

        imported_rules.append({
            "keywords": keywords,
            "reply": reply_text,
        })

    return imported_rules, skipped_rows


def parse_selection_ranges(text: str, total_count: int) -> List[int]:
    if total_count <= 0:
        return []

    selection_text = text.strip()
    if not selection_text:
        return []

    indices = set()

    for segment in re.split(r"[,，;；\s]+", selection_text):
        if not segment:
            continue

        if "-" in segment:
            start_text, end_text = segment.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"无效的区间: {segment}")

            start = int(start_text)
            end = int(end_text)
            if start <= 0 or end <= 0:
                raise ValueError("序号必须从 1 开始")
            if start > end:
                start, end = end, start

            start = max(1, start)
            end = min(total_count, end)
            for index in range(start - 1, end):
                indices.add(index)
            continue

        if not segment.isdigit():
            raise ValueError(f"无效的序号: {segment}")

        index = int(segment)
        if index <= 0:
            raise ValueError("序号必须从 1 开始")
        if index <= total_count:
            indices.add(index - 1)

    return sorted(indices)


def _load_csv_rows(filepath: str) -> List[List[str]]:
    rows = []
    with open(filepath, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append([(cell or "").strip() for cell in row[:2]])
    return rows


def _load_xlsx_rows(filepath: str) -> List[List[str]]:
    with zipfile.ZipFile(filepath, "r") as workbook:
        shared_strings = _load_shared_strings(workbook)
        sheet_path = _get_first_worksheet_path(workbook)
        namespace = {"main": EXCEL_MAIN_NS}
        root = ET.fromstring(workbook.read(sheet_path))
        rows = []

        for row_element in root.findall(".//main:sheetData/main:row", namespace):
            row_values = {1: "", 2: ""}
            for cell in row_element.findall("main:c", namespace):
                column_index = _get_excel_column_index(cell.attrib.get("r", ""))
                if column_index not in row_values:
                    continue
                row_values[column_index] = _get_excel_cell_value(cell, shared_strings, namespace)
            rows.append([row_values[1], row_values[2]])

    return rows


def _load_shared_strings(workbook: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    namespace = {"main": EXCEL_MAIN_NS}
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    shared_strings = []
    for item in root.findall("main:si", namespace):
        text_segments = [node.text or "" for node in item.findall(".//main:t", namespace)]
        shared_strings.append("".join(text_segments))
    return shared_strings


def _get_first_worksheet_path(workbook: zipfile.ZipFile) -> str:
    workbook_path = "xl/workbook.xml"
    rels_path = "xl/_rels/workbook.xml.rels"
    namespace = {
        "main": EXCEL_MAIN_NS,
        "rel": PACKAGE_REL_NS,
    }

    if workbook_path in workbook.namelist() and rels_path in workbook.namelist():
        workbook_root = ET.fromstring(workbook.read(workbook_path))
        first_sheet = workbook_root.find("main:sheets/main:sheet", {"main": EXCEL_MAIN_NS})
        if first_sheet is not None:
            relationship_id = first_sheet.attrib.get(f"{{{EXCEL_REL_NS}}}id")
            rels_root = ET.fromstring(workbook.read(rels_path))
            for relationship in rels_root.findall("rel:Relationship", namespace):
                if relationship.attrib.get("Id") != relationship_id:
                    continue
                target = (relationship.attrib.get("Target") or "").lstrip("/")
                if not target.startswith("xl/"):
                    target = f"xl/{target}"
                return target

    worksheet_paths = sorted(
        name for name in workbook.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    if not worksheet_paths:
        raise ValueError("Excel 文件中没有找到工作表")
    return worksheet_paths[0]


def _get_excel_cell_value(cell, shared_strings: List[str], namespace: Dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", namespace))

    value_node = cell.find("main:v", namespace)
    if value_node is None or value_node.text is None:
        return ""

    if cell_type == "s":
        shared_index = int(value_node.text)
        if 0 <= shared_index < len(shared_strings):
            return shared_strings[shared_index]
        return ""

    return value_node.text


def _get_excel_column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    if not letters:
        return -1

    column_index = 0
    for letter in letters:
        column_index = column_index * 26 + (ord(letter) - ord("A") + 1)
    return column_index


def _looks_like_rule_header(row: Sequence[str]) -> bool:
    if len(row) < 2:
        return False

    keyword_header = _normalize_header_text(row[0])
    reply_header = _normalize_header_text(row[1])
    return keyword_header in {"关键词", "keyword", "keywords", "触发词"} and reply_header in {
        "回复",
        "回复内容",
        "reply",
        "content",
        "response",
    }


def _normalize_header_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def build_row_selection_range(anchor_row: int, target_row: int) -> List[int]:
    if anchor_row < 0 or target_row < 0:
        raise ValueError("row index must be non-negative")

    start_row = min(anchor_row, target_row)
    end_row = max(anchor_row, target_row)
    return list(range(start_row, end_row + 1))


def apply_checked_indices(checked_states: Sequence[bool], indices: Sequence[int], checked: bool = True) -> List[bool]:
    updated_states = list(checked_states)

    for index in indices:
        if 0 <= index < len(updated_states):
            updated_states[index] = checked

    return updated_states


def merge_flag_bits(base_flags: FlagT, *required_bits: FlagT) -> FlagT:
    merged_flags = base_flags
    for bit in required_bits:
        merged_flags = merged_flags | bit
    return merged_flags


def ensure_flag_bits(base_flags: int, *required_bits: int) -> int:
    return merge_flag_bits(base_flags, *required_bits)


def find_item_index_by_id(items: Sequence[object], item_id: str) -> int:
    for index, item in enumerate(items):
        if getattr(item, "id", None) == item_id:
            return index
    return -1


def can_move_adjacent_row(current_index: int, item_count: int, step: int) -> bool:
    if item_count <= 0:
        return False
    if not 0 <= current_index < item_count:
        return False
    if step == 0:
        return False

    target_index = current_index + step
    return 0 <= target_index < item_count


def get_adjacent_row_index(current_index: int, item_count: int, step: int) -> int:
    if item_count <= 0:
        raise ValueError("item_count must be positive")
    if not 0 <= current_index < item_count:
        raise IndexError("current_index out of range")
    if step == 0:
        return current_index

    target_index = current_index + step
    if target_index < 0:
        return 0
    if target_index >= item_count:
        return item_count - 1
    return target_index


def normalize_reorder_target_row(source_index: int, target_index: int, item_count: int) -> int:
    if item_count <= 0:
        raise ValueError("item_count must be positive")
    if not 0 <= source_index < item_count:
        raise IndexError("source_index out of range")
    if not 0 <= target_index <= item_count:
        raise IndexError("target_index out of range")

    normalized_target = target_index
    if source_index < normalized_target:
        normalized_target -= 1
    if normalized_target >= item_count:
        normalized_target = item_count - 1
    return normalized_target


def replace_item_preserving_order(items: Sequence[T], index: int, new_item: T) -> List[T]:
    copied_items = list(items)
    copied_items[index] = new_item
    return copied_items


def move_item_in_list(items: Sequence[T], source_index: int, target_index: int) -> List[T]:
    copied_items = list(items)

    if not 0 <= source_index < len(copied_items):
        raise IndexError("source_index out of range")
    if not 0 <= target_index < len(copied_items):
        raise IndexError("target_index out of range")

    item = copied_items.pop(source_index)
    copied_items.insert(target_index, item)
    return copied_items
