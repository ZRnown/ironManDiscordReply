import unittest
from dataclasses import dataclass
import tempfile
import zipfile
from pathlib import Path

from src.gui_helpers import (
    apply_checked_indices,
    build_row_selection_range,
    can_move_adjacent_row,
    ensure_flag_bits,
    find_item_index_by_id,
    get_adjacent_row_index,
    merge_flag_bits,
    move_item_in_list,
    normalize_reorder_target_row,
    parse_channel_ids,
    parse_rule_import_file,
    parse_selection_ranges,
    replace_item_preserving_order,
    split_keywords,
)


class SplitKeywordsTests(unittest.TestCase):
    def test_supports_multiple_separators(self):
        self.assertEqual(
            split_keywords(" hello，world; foo；bar\n baz "),
            ["hello", "world", "foo", "bar", "baz"],
        )


class ParseChannelIdsTests(unittest.TestCase):
    def test_supports_multiple_separators_and_deduplicates(self):
        self.assertEqual(
            parse_channel_ids("123, 456\n789；456 123"),
            [123, 456, 789],
        )

    def test_rejects_non_numeric_values(self):
        with self.assertRaises(ValueError):
            parse_channel_ids("123, abc")


class ParseRuleImportFileTests(unittest.TestCase):
    def test_imports_csv_using_first_two_columns_and_skips_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "rules.csv"
            csv_path.write_text(
                "关键词,回复内容,其他列\n"
                "hello,hi there,ignore me\n"
                "world,hello world,\n"
                ",missing keyword,\n",
                encoding="utf-8",
            )

            imported_rules, skipped_rows = parse_rule_import_file(str(csv_path))

            self.assertEqual(
                imported_rules,
                [
                    {"keywords": ["hello"], "reply": "hi there"},
                    {"keywords": ["world"], "reply": "hello world"},
                ],
            )
            self.assertEqual(skipped_rows, 1)

    def test_imports_xlsx_using_first_two_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            xlsx_path = Path(temp_dir) / "rules.xlsx"
            build_test_xlsx(
                xlsx_path,
                rows=[
                    ["关键词", "回复内容"],
                    ["hello, hi", "welcome"],
                    ["bye", "see you"],
                ],
            )

            imported_rules, skipped_rows = parse_rule_import_file(str(xlsx_path))

            self.assertEqual(
                imported_rules,
                [
                    {"keywords": ["hello", "hi"], "reply": "welcome"},
                    {"keywords": ["bye"], "reply": "see you"},
                ],
            )
            self.assertEqual(skipped_rows, 0)

    def test_rejects_unsupported_file_types(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            txt_path = Path(temp_dir) / "rules.txt"
            txt_path.write_text("hello,world", encoding="utf-8")

            with self.assertRaises(ValueError):
                parse_rule_import_file(str(txt_path))


class ParseSelectionRangesTests(unittest.TestCase):
    def test_parses_single_values_and_ranges(self):
        self.assertEqual(
            parse_selection_ranges("1-3, 5, 8-10", total_count=12),
            [0, 1, 2, 4, 7, 8, 9],
        )

    def test_clamps_ranges_to_available_rows(self):
        self.assertEqual(
            parse_selection_ranges("3-8", total_count=5),
            [2, 3, 4],
        )

    def test_rejects_invalid_segments(self):
        with self.assertRaises(ValueError):
            parse_selection_ranges("1-two", total_count=10)


class ReplaceItemPreservingOrderTests(unittest.TestCase):
    def test_replaces_item_without_changing_neighbor_order(self):
        original = ["acc-1", "acc-2", "acc-3"]

        replaced = replace_item_preserving_order(original, 1, "acc-new")

        self.assertEqual(replaced, ["acc-1", "acc-new", "acc-3"])
        self.assertEqual(original, ["acc-1", "acc-2", "acc-3"])


@dataclass
class FakeIdentifiableItem:
    id: str


class FindItemIndexByIdTests(unittest.TestCase):
    def test_returns_current_index_for_matching_id(self):
        items = [
            FakeIdentifiableItem(id="rule-2"),
            FakeIdentifiableItem(id="rule-3"),
            FakeIdentifiableItem(id="rule-1"),
        ]

        self.assertEqual(find_item_index_by_id(items, "rule-1"), 2)

    def test_returns_negative_one_when_id_is_missing(self):
        items = [
            FakeIdentifiableItem(id="rule-1"),
            FakeIdentifiableItem(id="rule-2"),
        ]

        self.assertEqual(find_item_index_by_id(items, "rule-9"), -1)


class BuildRowSelectionRangeTests(unittest.TestCase):
    def test_builds_inclusive_range_when_target_is_below_anchor(self):
        self.assertEqual(build_row_selection_range(2, 5), [2, 3, 4, 5])

    def test_builds_inclusive_range_when_target_is_above_anchor(self):
        self.assertEqual(build_row_selection_range(5, 2), [2, 3, 4, 5])


class ApplyCheckedIndicesTests(unittest.TestCase):
    def test_checks_requested_indices_without_touching_others(self):
        self.assertEqual(
            apply_checked_indices([False, False, True, False], [0, 1], checked=True),
            [True, True, True, False],
        )

    def test_unchecks_requested_indices(self):
        self.assertEqual(
            apply_checked_indices([True, True, True, False], [1, 2], checked=False),
            [True, False, False, False],
        )


class EnsureFlagBitsTests(unittest.TestCase):
    def test_adds_missing_bits_without_losing_existing_bits(self):
        self.assertEqual(
            ensure_flag_bits(0b001, 0b010, 0b100),
            0b111,
        )


class FakeFlag:
    def __init__(self, bits: int):
        self.bits = bits

    def __or__(self, other):
        return FakeFlag(self.bits | other.bits)


class MergeFlagBitsTests(unittest.TestCase):
    def test_supports_flag_objects_that_do_not_implement_int(self):
        merged = merge_flag_bits(FakeFlag(0b001), FakeFlag(0b010), FakeFlag(0b100))

        self.assertEqual(merged.bits, 0b111)


class MoveItemInListTests(unittest.TestCase):
    def test_moves_item_downward_to_new_row(self):
        original = ["rule-1", "rule-2", "rule-3", "rule-4"]

        moved = move_item_in_list(original, 1, 3)

        self.assertEqual(moved, ["rule-1", "rule-3", "rule-4", "rule-2"])
        self.assertEqual(original, ["rule-1", "rule-2", "rule-3", "rule-4"])

    def test_moves_item_upward_to_new_row(self):
        original = ["rule-1", "rule-2", "rule-3", "rule-4"]

        moved = move_item_in_list(original, 3, 1)

        self.assertEqual(moved, ["rule-1", "rule-4", "rule-2", "rule-3"])


class NormalizeReorderTargetRowTests(unittest.TestCase):
    def test_adjusts_downward_drop_to_final_insert_row(self):
        self.assertEqual(
            normalize_reorder_target_row(source_index=1, target_index=4, item_count=5),
            3,
        )

    def test_keeps_upward_drop_row_unchanged(self):
        self.assertEqual(
            normalize_reorder_target_row(source_index=4, target_index=1, item_count=5),
            1,
        )

    def test_maps_append_drop_to_last_insert_row(self):
        self.assertEqual(
            normalize_reorder_target_row(source_index=0, target_index=5, item_count=5),
            4,
        )


class GetAdjacentRowIndexTests(unittest.TestCase):
    def test_moves_selected_row_up_by_one(self):
        self.assertEqual(
            get_adjacent_row_index(current_index=2, item_count=4, step=-1),
            1,
        )

    def test_moves_selected_row_down_by_one(self):
        self.assertEqual(
            get_adjacent_row_index(current_index=1, item_count=4, step=1),
            2,
        )

    def test_keeps_top_row_when_moving_up(self):
        self.assertEqual(
            get_adjacent_row_index(current_index=0, item_count=4, step=-1),
            0,
        )

    def test_keeps_bottom_row_when_moving_down(self):
        self.assertEqual(
            get_adjacent_row_index(current_index=3, item_count=4, step=1),
            3,
        )


class CanMoveAdjacentRowTests(unittest.TestCase):
    def test_allows_middle_row_to_move_up(self):
        self.assertTrue(
            can_move_adjacent_row(current_index=2, item_count=4, step=-1),
        )

    def test_blocks_top_row_from_moving_up(self):
        self.assertFalse(
            can_move_adjacent_row(current_index=0, item_count=4, step=-1),
        )

    def test_blocks_bottom_row_from_moving_down(self):
        self.assertFalse(
            can_move_adjacent_row(current_index=3, item_count=4, step=1),
        )


def build_test_xlsx(path: Path, rows):
    shared_strings = []
    shared_index = {}

    def get_shared_string_index(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    worksheet_rows = []
    for row_number, row_values in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row_values, start=1):
            if value is None:
                continue
            cell_ref = f"{chr(64 + column_index)}{row_number}"
            shared_string_index = get_shared_string_index(str(value))
            cells.append(
                f'<c r="{cell_ref}" t="s"><v>{shared_string_index}</v></c>'
            )
        worksheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    shared_strings_xml = (
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        + "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
        + "</sst>"
    )
    sheet_xml = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(worksheet_rows)
        + "</sheetData></worksheet>"
    )

    with zipfile.ZipFile(path, "w") as workbook:
        workbook.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        workbook.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        workbook.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
    </sheets>
</workbook>""",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>""",
        )
        workbook.writestr("xl/sharedStrings.xml", shared_strings_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)


if __name__ == "__main__":
    unittest.main()
