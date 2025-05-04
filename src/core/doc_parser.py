from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest, ContentFormat
from typing import List, Dict
from ..models import Block, BoundingBox, Chunk
from ..config import AZURE_DI_ENDPOINT, AZURE_DI_KEY
import fitz # PyMuPDF for extracting pages
import io
import time
import uuid

class AzureDocumentParser:
    """Uses Azure Document Intelligence to extract text blocks and coordinates."""

    def __init__(self):
        if not AZURE_DI_ENDPOINT or not AZURE_DI_KEY:
            raise ValueError("Azure Document Intelligence endpoint or key is not configured.")
        self.client = DocumentIntelligenceClient(endpoint=AZURE_DI_ENDPOINT, credential=AzureKeyCredential(AZURE_DI_KEY))

    def extract_blocks_for_chunk(self, pdf_path: str, chunk: Chunk) -> List[Block]:
        """Extracts text blocks for the pages specified in the chunk.

        Args:
            pdf_path: Path to the original PDF file.
            chunk: The Chunk object defining the page range.

        Returns:
            A list of Block objects extracted from the specified pages.
        """
        extracted_blocks: List[Block] = []
        start_page, end_page = chunk.page_numbers # 1-based
        page_indices = list(range(start_page - 1, end_page)) # 0-based indices for PyMuPDF

        try:
            doc = fitz.open(pdf_path)
            if not page_indices:
                print(f"Chunk {chunk.id}: No pages to process.")
                return []

            # Create a temporary in-memory PDF with only the pages for this chunk
            temp_pdf_bytes = self._create_temp_pdf_for_chunk(doc, page_indices)
            doc.close()

            if not temp_pdf_bytes:
                print(f"Chunk {chunk.id}: Failed to create temporary PDF for analysis.")
                return []

            print(f"Chunk {chunk.id}: Sending pages {start_page}-{end_page} to Document Intelligence...")
            # Use Read model (formerly Layout)
            poller = self.client.begin_analyze_document(
                "prebuilt-read", # Use the "read" model for text extraction
                AnalyzeDocumentRequest(bytes_source=temp_pdf_bytes),
                output_content_format=ContentFormat.MARKDOWN # Or TEXT, depending on downstream needs
            )
            result: AnalyzeResult = poller.result()
            print(f"Chunk {chunk.id}: Document Intelligence analysis complete.")

            if result.pages:
                for page_result in result.pages:
                    original_page_number = start_page + page_result.page_number - 1 # DI page_number is 1-based within the submitted doc
                    if page_result.lines:
                         # --- Simple block-per-line approach (Merge later) ---
                         # You might want a more sophisticated approach based on paragraphs if available
                        for line in page_result.lines:
                            if line.bounding_regions and line.content:
                                # Assuming the first bounding region is the most relevant
                                # DI coordinates are typically top-left based, relative to page dimensions
                                region = line.bounding_regions[0]
                                # DI gives polygon (points), calculate simple bbox
                                x_coords = [p.x for p in region.polygon]
                                y_coords = [p.y for p in region.polygon]
                                bbox = BoundingBox(
                                    x=min(x_coords),
                                    y=min(y_coords),
                                    width=max(x_coords) - min(x_coords),
                                    height=max(y_coords) - min(y_coords)
                                )
                                block_id = f"p{original_page_number}_l{line.spans[0].offset if line.spans else uuid.uuid4()}"
                                block = Block(
                                    id=block_id,
                                    text=line.content.strip(),
                                    bbox=bbox,
                                    page_number=original_page_number
                                )
                                extracted_blocks.append(block)
            else:
                 print(f"Chunk {chunk.id}: No pages found in Document Intelligence result.")


        except Exception as e:
            print(f"Error during Document Intelligence processing for chunk {chunk.id} (Pages {start_page}-{end_page}): {e}")
            # Consider retry logic or specific error handling

        print(f"Chunk {chunk.id}: Extracted {len(extracted_blocks)} blocks.")
        return extracted_blocks

    def _create_temp_pdf_for_chunk(self, original_doc: fitz.Document, page_indices: List[int]) -> bytes | None:
        """Creates an in-memory PDF containing only the specified pages."""
        try:
            temp_doc = fitz.open() # Create a new empty PDF
            temp_doc.insert_pdf(original_doc, from_page=min(page_indices), to_page=max(page_indices), show_progress=0)
            # Save to memory
            pdf_bytes = temp_doc.tobytes(garbage=4, deflate=True)
            temp_doc.close()
            return pdf_bytes
        except Exception as e:
            print(f"Error creating temporary PDF for pages {min(page_indices)+1}-{max(page_indices)+1}: {e}")
            return None 