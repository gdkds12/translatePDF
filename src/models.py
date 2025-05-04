from pydantic import BaseModel, Field
from typing import List, Tuple

class BoundingBox(BaseModel):
    """Represents the bounding box of a text block."""
    x: float
    y: float
    width: float
    height: float

class Block(BaseModel):
    """Represents a text block extracted from a page."""
    id: str = Field(..., description="Unique identifier for the block")
    text: str
    bbox: BoundingBox
    page_number: int
    # Potentially add line/paragraph info if needed from DI

class MergedBlock(BaseModel):
    """Represents a block of text after merging (e.g., a paragraph)."""
    id: str # Could be the ID of the first original block
    text: str
    original_block_ids: List[str]
    page_number: int
    # BBox might need recalculation or represent the union of original boxes

class TranslatedBlock(BaseModel):
    """Represents a block with its translated text and original position."""
    id: str # Matches original Block or MergedBlock ID
    original_text: str
    translated_text: str
    bbox: BoundingBox # Crucial for layout
    page_number: int

class Chunk(BaseModel):
    """Represents a chunk of pages to be processed."""
    id: int
    page_numbers: Tuple[int, int] # Start and end page number (1-based, inclusive)
    # Potentially store file path or reference 