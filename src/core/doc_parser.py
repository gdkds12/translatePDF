from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult, AnalyzeDocumentRequest,
    DocumentAnalysisFeature # Import features enum
)
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
                output_content_format="markdown",
                features=[DocumentAnalysisFeature.OCR_HIGH_RESOLUTION] # Request only basic OCR features
            )
            result: AnalyzeResult = poller.result()
            print(f"Chunk {chunk.id}: Document Intelligence analysis complete.")

            if result.pages:
                print(f"Chunk {chunk.id}: Processing {len(result.pages)} pages from DI result...")
                for page_result in result.pages:
                    original_page_number = start_page + page_result.page_number - 1 # DI page_number is 1-based within the submitted doc
                    print(f"  Processing DI page {page_result.page_number} (Original page: {original_page_number}). Found {len(page_result.lines) if page_result.lines else 0} lines.")
                    if page_result.lines:
                         # --- Simple block-per-line approach (Merge later) ---
                         # You might want a more sophisticated approach based on paragraphs if available
                        for idx, line in enumerate(page_result.lines):
                            # Use polygon instead of bounding_regions for stable versions
                            if line.polygon and line.content:
                                print(f"    Line {idx}: Content='{line.content[:30]}...' Polygon found.")
                                # DI gives polygon (points), calculate simple bbox
                                # Polygon is a flat list [x0, y0, x1, y1, ...]
                                if len(line.polygon) >= 8: # Ensure at least 4 points (quadrilateral)
                                    x_coords = [line.polygon[i] for i in range(0, len(line.polygon), 2)]
                                    y_coords = [line.polygon[i] for i in range(1, len(line.polygon), 2)]
                                    
                                    min_x = min(x_coords)
                                    min_y = min(y_coords)
                                    max_x = max(x_coords)
                                    max_y = max(y_coords)
                                    
                                    bbox = BoundingBox(
                                        x=min_x,
                                        y=min_y,
                                        width=max_x - min_x,
                                        height=max_y - min_y
                                    )
                                    block_id = f"p{original_page_number}_l{line.spans[0].offset if line.spans else uuid.uuid4()}"
                                    block = Block(
                                        id=block_id,
                                        text=line.content.strip(),
                                        bbox=bbox,
                                        page_number=original_page_number
                                    )
                                    extracted_blocks.append(block)
                                    # print(f"      Created Block ID: {block_id}, BBox: ({bbox.x:.2f},{bbox.y:.2f}, w:{bbox.width:.2f}, h:{bbox.height:.2f})")
                                else:
                                     print(f"    Line {idx}: Polygon found but has insufficient points ({len(line.polygon)} points). Skipping.")

                            else:
                                print(f"    Line {idx}: Skipping line - Missing polygon or content. Content: '{line.content[:30] if line.content else 'N/A'}', Polygon: {'Exists' if line.polygon else 'Missing'}")
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