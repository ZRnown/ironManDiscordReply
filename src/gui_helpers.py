import re
from typing import List, Sequence, TypeVar

T = TypeVar("T")
FlagT = TypeVar("FlagT")


def split_keywords(text: str) -> List[str]:
    return [keyword.strip() for keyword in re.split(r"[,\n，;；]+", text) if keyword.strip()]


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
