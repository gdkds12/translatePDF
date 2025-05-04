import fitz # PyMuPDF
from typing import List, Dict, Optional
from ..models import TranslatedBlock
from .layout_engine import LayoutEngine

class PageRenderer:
    """Renders individual PDF pages with translated text overlaid."""

    def __init__(self, layout_engine: LayoutEngine):
        self.layout_engine = layout_engine

    def render_pages_for_chunk(self, original_pdf_path: str, 
                               page_numbers: List[int], 
                               translated_blocks_by_page: Dict[int, List[TranslatedBlock]]) -> Dict[int, bytes]:
        """Renders PDF pages for a given chunk.

        Args:
            original_pdf_path: Path to the source PDF.
            page_numbers: List of 1-based page numbers in this chunk.
            translated_blocks_by_page: A dictionary mapping page number to its translated blocks.

        Returns:
            A dictionary mapping page number (1-based) to the rendered page content (bytes).
        """
        rendered_pages: Dict[int, bytes] = {}

        for page_num in page_numbers:
            blocks_for_page = translated_blocks_by_page.get(page_num, [])
            print(f"Rendering page {page_num} with {len(blocks_for_page)} translated blocks...")
            
            rendered_page_bytes = self.layout_engine.overlay_text_on_page(
                original_pdf_path=original_pdf_path,
                page_num=page_num,
                translated_blocks=blocks_for_page
            )
            
            if rendered_page_bytes:
                rendered_pages[page_num] = rendered_page_bytes
                print(f"Page {page_num} rendered successfully.")
            else:
                print(f"Failed to render page {page_num}. It might be excluded from the final PDF.")
                # Optionally: copy the original page instead of skipping
                # rendered_pages[page_num] = self._get_original_page_bytes(original_pdf_path, page_num)

        return rendered_pages

    def _get_original_page_bytes(self, pdf_path: str, page_num: int) -> Optional[bytes]:
        """Helper to get the raw bytes of an original page."""
        try:
            doc = fitz.open(pdf_path)
            if 0 < page_num <= len(doc):
                page = doc.load_page(page_num - 1)
                # Create a new single-page doc to save bytes correctly
                temp_doc = fitz.open()
                temp_doc.insert_pdf(doc, from_page=page_num-1, to_page=page_num-1)
                page_bytes = temp_doc.tobytes()
                temp_doc.close()
                doc.close()
                return page_bytes
            else:
                doc.close()
                return None
        except Exception as e:
            print(f"Error getting original page {page_num} bytes: {e}")
            return None 