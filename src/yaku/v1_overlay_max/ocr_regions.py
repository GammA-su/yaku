from __future__ import annotations

from yaku.ocr.base import OCRBox
from yaku.ocr.japanese_filter import contains_japanese, clean_ocr_text


def sort_ocr_boxes_reading_order(boxes: list[OCRBox]) -> list[OCRBox]:
    """Sort OCR boxes in standard reading order: top-to-bottom, left-to-right.

    Lines are grouped dynamically using vertical overlap (top y alignment).
    """
    if not boxes:
        return []

    # Sort boxes by top y coordinate first
    sorted_by_y = sorted(boxes, key=lambda b: b.box[1])
    lines: list[list[OCRBox]] = []

    for box in sorted_by_y:
        x, y, w, h = box.box
        # Check if this box fits in any existing line based on vertical overlap/proximity
        placed = False
        for line in lines:
            # Check overlap with the first box of the line
            ref_box = line[0].box
            ref_y = ref_box[1]
            ref_h = ref_box[3]

            # overlap check
            overlap = min(y + h, ref_y + ref_h) - max(y, ref_y)
            min_h = min(h, ref_h)

            if overlap > 0 and overlap >= 0.4 * min_h:
                line.append(box)
                placed = True
                break

        if not placed:
            lines.append([box])

    # Sort each line horizontally (by x), and then flatten the list of lines
    flat_sorted: list[OCRBox] = []
    # Sort lines by their average or minimum Y coordinate
    lines.sort(key=lambda line: min(b.box[1] for b in line))

    for line in lines:
        line.sort(key=lambda b: b.box[0])
        flat_sorted.extend(line)

    return flat_sorted


def merge_nearby_ocr_boxes(boxes: list[OCRBox], distance_px: int) -> list[OCRBox]:
    """Merge OCR boxes on the same line when they are horizontally close."""
    if not boxes:
        return []

    # Sort in reading order first to ensure proper adjacency
    sorted_boxes = sort_ocr_boxes_reading_order(boxes)
    n = len(sorted_boxes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Build connected components for merging
    for i in range(n):
        for j in range(i + 1, n):
            box_a = sorted_boxes[i].box
            box_b = sorted_boxes[j].box

            # Vertical overlap check to ensure they are on the same line
            y_overlap = min(box_a[1] + box_a[3], box_b[1] + box_b[3]) - max(box_a[1], box_b[1])
            min_h = min(box_a[3], box_b[3])

            if y_overlap > 0 and y_overlap >= 0.4 * min_h:
                # Horizontal gap check
                # Horizontal gap is the space between the right edge of one and left edge of another
                gap = max(box_a[0], box_b[0]) - min(box_a[0] + box_a[2], box_b[0] + box_b[2])
                if gap <= distance_px:
                    union(i, j)

    # Group box indexes by their root parent
    groups: dict[int, list[OCRBox]] = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(sorted_boxes[i])

    merged: list[OCRBox] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
        else:
            # Sort the group in reading order
            sorted_group = sort_ocr_boxes_reading_order(group)
            min_x = min(b.box[0] for b in sorted_group)
            min_y = min(b.box[1] for b in sorted_group)
            max_r = max(b.box[0] + b.box[2] for b in sorted_group)
            max_b = max(b.box[1] + b.box[3] for b in sorted_group)

            # Concatenate text. For Japanese text, standard is direct concatenation.
            merged_text = "".join(b.text for b in sorted_group)

            confs = [b.confidence for b in sorted_group if b.confidence is not None]
            avg_conf = sum(confs) / len(confs) if confs else None

            merged.append(
                OCRBox(
                    text=merged_text,
                    box=(min_x, min_y, max_r - min_x, max_b - min_y),
                    confidence=avg_conf,
                )
            )

    return sort_ocr_boxes_reading_order(merged)


def filter_ocr_boxes(boxes: list[OCRBox], config: any) -> list[OCRBox]:
    """Filter boxes based on Japanese presence, minimum length, and maximum region count."""
    japanese_only = getattr(config, "japanese_only", True)
    min_text_chars = getattr(config, "min_text_chars", 1)
    max_regions = getattr(config, "max_regions", 30)

    filtered: list[OCRBox] = []
    for b in boxes:
        cleaned = clean_ocr_text(b.text)
        if not cleaned:
            continue
        if len(cleaned) < min_text_chars:
            continue
        if japanese_only and not contains_japanese(cleaned):
            continue

        filtered.append(OCRBox(text=cleaned, box=b.box, confidence=b.confidence))

    return filtered[:max_regions]
