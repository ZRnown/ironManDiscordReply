import unittest

from src.gui_helpers import (
    apply_checked_indices,
    build_row_selection_range,
    ensure_flag_bits,
    move_item_in_list,
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


if __name__ == "__main__":
    unittest.main()
