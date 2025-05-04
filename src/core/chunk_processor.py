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
        """Processes a single chunk through the entire pipeline.

        Args:
            pdf_path: Path to the original PDF file.
            chunk: The Chunk object to process.

        Returns:
            A dictionary mapping 1-based page number to the rendered page content (bytes)
            for this chunk.
        """
        print(f"--- Starting processing for Chunk {chunk.id} (Pages {chunk.page_numbers[0]}-{chunk.page_numbers[1]}) ---")
        start_time = time.time()

        # 1. Extract Blocks
        blocks: List[Block] = self.doc_parser.extract_blocks_for_chunk(pdf_path, chunk)
        if not blocks:
            print(f"Chunk {chunk.id}: No text blocks extracted. Skipping further processing.")
            return {}
        original_blocks_map: Dict[str, Block] = {b.id: b for b in blocks}

        # 2. Merge Blocks (Current implementation is placeholder)
        # Group blocks by page for merging and translation if needed, although current merge is simple
        blocks_by_page: Dict[int, List[Block]] = {}
        for block in blocks:
            blocks_by_page.setdefault(block.page_number, []).append(block)

        all_merged_blocks: List[MergedBlock] = [] 
        for page_num, page_blocks in blocks_by_page.items():
             merged_for_page = self.text_merger.merge_blocks(page_blocks)
             all_merged_blocks.extend(merged_for_page)
        
        if not all_merged_blocks:
            print(f"Chunk {chunk.id}: No merged blocks to translate. Skipping further processing.")
            return {}
        
        # 3. Translate Merged Blocks
        translated_blocks: List[TranslatedBlock] = self.translator.translate_blocks(all_merged_blocks, original_blocks_map)
        if not translated_blocks:
             print(f"Chunk {chunk.id}: Translation failed or produced no results. Skipping rendering.")
             return {}

        # Group translated blocks by page for rendering
        translated_blocks_by_page: Dict[int, List[TranslatedBlock]] = {}
        for t_block in translated_blocks:
            translated_blocks_by_page.setdefault(t_block.page_number, []).append(t_block)

        # 4. Render Pages (Layout + Page Rendering)
        chunk_page_numbers = list(range(chunk.page_numbers[0], chunk.page_numbers[1] + 1))
        rendered_pages: Dict[int, bytes] = self.page_renderer.render_pages_for_chunk(
            original_pdf_path=pdf_path,
            page_numbers=chunk_page_numbers,
            translated_blocks_by_page=translated_blocks_by_page
        )

        end_time = time.time()
        print(f"--- Finished processing Chunk {chunk.id}. Duration: {end_time - start_time:.2f} seconds ---")

        return rendered_pages

# Need to import time at the top
import time 