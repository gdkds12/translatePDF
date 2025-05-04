from typing import List, Tuple
from ..models import Block, MergedBlock, BoundingBox
import re

# Constants for merging logic (tune these values)
VERTICAL_TOLERANCE_FACTOR = 0.5 # Allowable vertical gap relative to block height
HORIZONTAL_OVERLAP_THRESHOLD = 0.1 # Minimum horizontal overlap required

class TextBlockMerger:
    """Merges individual text blocks into more coherent units (e.g., paragraphs)."""

    def merge_blocks(self, blocks: List[Block]) -> List[MergedBlock]:
        """Merges blocks based on proximity, page number, etc.

        Args:
            blocks: A list of Block objects, typically from a single page.

        Returns:
            A list of MergedBlock objects.
        """
        if not blocks:
            return []

        # Sort blocks primarily by top coordinate (y), then left coordinate (x)
        blocks.sort(key=lambda b: (b.bbox.y, b.bbox.x))

        merged: List[MergedBlock] = []
        current_merged_text = ""
        current_original_ids: List[str] = []
        current_page_number = -1
        last_block: Block | None = None

        for i, block in enumerate(blocks):
            if not last_block: # First block
                current_merged_text = self._preprocess_text(block.text)
                current_original_ids = [block.id]
                current_page_number = block.page_number
                last_block = block
            elif self._should_merge(last_block, block):
                # Check for hyphenated word at the end of the last block's text
                processed_last_text = self._handle_hyphenation(last_block.text)
                
                # Append preprocessed text
                current_merged_text += (" " + self._preprocess_text(block.text) if not processed_last_text.endswith('-') else self._preprocess_text(block.text))
                current_original_ids.append(block.id)
                # Update last_block for next comparison (bbox doesn't need update for logic)
                last_block = block
            else: # Start a new merged block
                # Save the previous merged block
                merged.append(MergedBlock(
                    id=f"merged_{current_original_ids[0]}",
                    text=current_merged_text.strip(),
                    original_block_ids=current_original_ids,
                    page_number=current_page_number
                    # TODO: Optionally calculate union Bbox here
                ))
                # Reset for the new block
                current_merged_text = self._preprocess_text(block.text)
                current_original_ids = [block.id]
                current_page_number = block.page_number
                last_block = block

        # Add the last processed merged block
        if current_original_ids:
            merged.append(MergedBlock(
                id=f"merged_{current_original_ids[0]}",
                text=current_merged_text.strip(),
                original_block_ids=current_original_ids,
                page_number=current_page_number
            ))

        print(f"Processed {len(blocks)} blocks into {len(merged)} merged blocks.")
        return merged

    def _should_merge(self, block1: Block, block2: Block) -> bool:
        """Determines if two blocks should be merged based on spatial proximity."""
        # Must be on the same page
        if block1.page_number != block2.page_number:
            return False

        b1_bottom = block1.bbox.y + block1.bbox.height
        b2_top = block2.bbox.y
        vertical_gap = b2_top - b1_bottom

        # Check vertical proximity (allow small gap or minor overlap)
        # Use average height for tolerance calculation
        avg_height = (block1.bbox.height + block2.bbox.height) / 2
        if not (-avg_height * 0.1 < vertical_gap < avg_height * VERTICAL_TOLERANCE_FACTOR):
             return False

        # Check horizontal overlap or close alignment
        b1_left, b1_right = block1.bbox.x, block1.bbox.x + block1.bbox.width
        b2_left, b2_right = block2.bbox.x, block2.bbox.x + block2.bbox.width
        
        overlap_start = max(b1_left, b2_left)
        overlap_end = min(b1_right, b2_right)
        horizontal_overlap = max(0, overlap_end - overlap_start)

        # Require some horizontal overlap or very close horizontal start points
        min_width = min(block1.bbox.width, block2.bbox.width)
        if horizontal_overlap < min_width * HORIZONTAL_OVERLAP_THRESHOLD and abs(b1_left - b2_left) > avg_height * 0.5: # Allow some horizontal shift based on line height
             return False

        # Simple check: merge if text doesn't end with sentence-ending punctuation.
        # More sophisticated checks (e.g., indentation) could be added.
        if block1.text.strip().endswith(('.', '!', '?')):
            return False

        return True


    def _handle_hyphenation(self, text: str) -> str:
         """Removes trailing hyphen if it seems to be for word splitting."""
         clean_text = text.strip()
         # Simple check: remove hyphen if it's at the end and preceded by a letter
         if clean_text.endswith('-') and len(clean_text) > 1 and clean_text[-2].isalpha():
              # Check if the part before hyphen is likely a word fragment (optional, more complex)
              return clean_text[:-1] # Remove hyphen
         return clean_text # Return original cleaned text

    def _preprocess_text(self, text: str) -> str:
        """Basic text preprocessing."""
        # Remove trailing hyphens potentially used for word splitting across lines
        processed_text = self._handle_hyphenation(text)
        # Normalize whitespace (replace multiple spaces/newlines with single space)
        processed_text = re.sub(r'\s+', ' ', processed_text).strip()
        return processed_text

    def _calculate_union_bbox(self, blocks: List[Block]) -> BoundingBox:
        """Calculates the bounding box enclosing all given blocks."""
        if not blocks:
            # Should not happen if called correctly
            return BoundingBox(x=0, y=0, width=0, height=0)

        min_x = min(b.bbox.x for b in blocks)
        min_y = min(b.bbox.y for b in blocks)
        max_right = max(b.bbox.x + b.bbox.width for b in blocks)
        max_bottom = max(b.bbox.y + b.bbox.height for b in blocks)

        return BoundingBox(
            x=min_x,
            y=min_y,
            width=max_right - min_x,
            height=max_bottom - min_y
        )

    # --- Potential helper methods for actual merging ---
    # def _is_vertically_close(block1: Block, block2: Block) -> bool:
    #     ...
    # def _is_horizontally_aligned(block1: Block, block2: Block) -> bool:
    #     ...
    # def _calculate_union_bbox(blocks: List[Block]) -> BoundingBox:
    #     ... 