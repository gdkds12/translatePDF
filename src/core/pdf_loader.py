import fitz # PyMuPDF
from typing import List, Tuple
from ..models import Chunk
import math

class PDFLoader:
    """Loads a PDF and divides it into processable chunks."""

    def __init__(self, chunk_size: int = 10):
        self.chunk_size = chunk_size

    def load_and_split(self, pdf_path: str) -> Tuple[List[Chunk], int]:
        """Loads the PDF, determines the total pages, and creates chunks.

        Args:
            pdf_path: Path to the input PDF file.

        Returns:
            A tuple containing:
                - A list of Chunk objects.
                - The total number of pages in the PDF.
        """
        chunks = []
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()

            if total_pages == 0:
                return [], 0

            num_chunks = math.ceil(total_pages / self.chunk_size)

            for i in range(num_chunks):
                start_page = i * self.chunk_size + 1
                end_page = min((i + 1) * self.chunk_size, total_pages)
                chunk = Chunk(id=i, page_numbers=(start_page, end_page))
                chunks.append(chunk)

            print(f"Loaded '{pdf_path}', {total_pages} pages, split into {num_chunks} chunks.")
            return chunks, total_pages

        except Exception as e:
            print(f"Error loading or splitting PDF '{pdf_path}': {e}")
            # Consider raising the exception or returning an empty list/error state
            return [], 0 