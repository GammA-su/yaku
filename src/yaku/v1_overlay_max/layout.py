from __future__ import annotations

from yaku.ocr.base import OCRBox


def compute_label_positions(
    boxes: list[OCRBox],
    label_sizes: list[tuple[int, int]],  # list of (width, height) for each label
    screen_width: int,
    screen_height: int,
    config: any,  # v1_overlay_max config section
) -> list[tuple[int, int]]:
    """Calculate overlay label screen positions near their OCR boxes.

    Ensures they don't go offscreen and resolves overlapping labels.
    """
    if not boxes or not label_sizes or len(boxes) != len(label_sizes):
        return []

    overlay_config = getattr(config, "overlay", None)
    anchor = getattr(overlay_config, "anchor", "right") if overlay_config else "right"
    padding = getattr(overlay_config, "padding", 6) if overlay_config else 6
    avoid_offscreen = getattr(overlay_config, "avoid_offscreen", True) if overlay_config else True

    positions: list[tuple[int, int]] = []

    for i, ob in enumerate(boxes):
        bx, by, bw, bh = ob.box
        lw, lh = label_sizes[i]

        if anchor == "right":
            lx = bx + bw + padding
            ly = by + (bh - lh) // 2
        elif anchor == "left":
            lx = bx - lw - padding
            ly = by + (bh - lh) // 2
        elif anchor == "top":
            lx = bx + (bw - lw) // 2
            ly = by - lh - padding
        elif anchor == "bottom":
            lx = bx + (bw - lw) // 2
            ly = by + bh + padding
        else:
            lx = bx + (bw - lw) // 2
            ly = by + (bh - lh) // 2

        if avoid_offscreen:
            if lx < 0:
                lx = 0
            if lx + lw > screen_width:
                lx = screen_width - lw
            if ly < 0:
                ly = 0
            if ly + lh > screen_height:
                ly = screen_height - lh

        positions.append((lx, ly))

    for i in range(len(positions)):
        lx, ly = positions[i]
        lw, lh = label_sizes[i]

        collision = True
        attempts = 0
        while collision and attempts < 30:
            collision = False
            for j in range(i):
                jx, jy = positions[j]
                jw, jh = label_sizes[j]

                if not (lx + lw <= jx or lx >= jx + jw or ly + lh <= jy or ly >= jy + jh):
                    collision = True
                    ly = jy + jh + 2
                    attempts += 1
                    break

            if collision and avoid_offscreen and ly + lh > screen_height:
                ly = screen_height - lh
                lx += 15
                if lx + lw > screen_width:
                    lx = 0
                collision = False
                break

        positions[i] = (lx, ly)

    return positions
