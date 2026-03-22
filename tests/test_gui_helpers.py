import unittest
from dataclasses import dataclass

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


if __name__ == "__main__":
    unittest.main()
