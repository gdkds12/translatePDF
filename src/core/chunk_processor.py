from typing import List, Dict
from ..models import Chunk, Block, MergedBlock, TranslatedBlock
from .doc_parser import AzureDocumentParser
from .text_merger import TextBlockMerger
from .translator import Translator
from .layout_engine import LayoutEngine
from .page_renderer import PageRenderer

class ChunkProcessor:
    """Orchestrates the processing pipeline for a single chunk of PDF pages."""

    def __init__(self,
                 doc_parser: AzureDocumentParser,
                 text_merger: TextBlockMerger,
                 translator: Translator,
                 layout_engine: LayoutEngine,
                 page_renderer: PageRenderer):
        self.doc_parser = doc_parser
        self.text_merger = text_merger
        self.translator = translator
        self.layout_engine = layout_engine # Needed by PageRenderer
        self.page_renderer = page_renderer

    def process_chunk(self, pdf_path: str, chunk: Chunk) -> Dict[int, bytes]:
        """Processes a single chunk: parse, merge, translate, render."""
        print(f"--- Starting processing for Chunk {chunk.id} (Pages {chunk.page_numbers[0]}-{chunk.page_numbers[1]}) ---")
        rendered_pages: Dict[int, bytes] = {}

        try:
            # 1. Parse with Document Intelligence
            print(f"Chunk {chunk.id}: Step 1 - Parsing document...")
            initial_blocks = self.doc_parser.extract_blocks_for_chunk(pdf_path, chunk)
            print(f"Chunk {chunk.id}: Step 1 - Parsing complete. Found {len(initial_blocks)} initial blocks.")
            if not initial_blocks:
                print(f"Chunk {chunk.id}: No text blocks extracted. Skipping further processing.")
                return {}
            original_blocks_map: Dict[str, Block] = {b.id: b for b in initial_blocks}

            # 2. Merge text blocks (Optional but recommended)
            print(f"Chunk {chunk.id}: Step 2 - Merging text blocks...")
            merged_blocks = self.text_merger.merge_blocks(initial_blocks)
            print(f"Chunk {chunk.id}: Step 2 - Merging complete. {len(merged_blocks)} blocks after merging.")

            # 3. Translate merged blocks
            print(f"Chunk {chunk.id}: Step 3 - Translating text blocks...")
            print(f"Chunk {chunk.id}: Calling translator for {len(merged_blocks)} blocks.")
            translated_blocks = self.translator.translate_blocks(merged_blocks, original_blocks_map)
            print(f"Chunk {chunk.id}: Translator returned {len(translated_blocks)} blocks.")
            print(f"Chunk {chunk.id}: Step 3 - Translation complete. {len(translated_blocks)} blocks translated.")
            if not translated_blocks:
                print(f"Chunk {chunk.id}: No blocks translated successfully. Skipping rendering.")
                return {}

            # 4. Render translated text onto original pages
            print(f"Chunk {chunk.id}: Step 4 - Rendering translated text onto pages...")
            unique_page_numbers = sorted(list(set(block.page_number for block in translated_blocks)))
            print(f"Chunk {chunk.id}: Rendering for pages: {unique_page_numbers}")
            
            for page_num in unique_page_numbers:
                 print(f"  Rendering page {page_num}...")
                 page_specific_blocks = [b for b in translated_blocks if b.page_number == page_num]
                 rendered_page_bytes = self.layout_engine.overlay_text_on_page(pdf_path, page_num, page_specific_blocks)
                 if rendered_page_bytes:
                     rendered_pages[page_num] = rendered_page_bytes
                     print(f"  Rendering page {page_num} complete ({len(rendered_page_bytes)} bytes).")
                 else:
                     print(f"  Warning: Rendering failed for page {page_num}.")
            
            print(f"Chunk {chunk.id}: Step 4 - Rendering complete. {len(rendered_pages)} pages rendered.")
            
        except Exception as e:
            # More robust error logging
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"Error processing chunk {chunk.id}. Type: {error_type}, Message: {error_msg}")
            import traceback
            print(f"Traceback:\n{traceback.format_exc()}")
            # Decide if we want to return partial results or empty dict on error
            # For now, returning empty on any chunk error for simplicity
            return {} 

        print(f"--- Finished processing for Chunk {chunk.id}. Returning {len(rendered_pages)} rendered pages. ---")
        return rendered_pages

# Need to import time at the top
import time 