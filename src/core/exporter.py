import fitz # PyMuPDF
from typing import Dict
import os

class Exporter:
    """Combines rendered pages and saves the final PDF."""

    def save_pdf(self, rendered_pages: Dict[int, bytes], total_pages: int, output_path: str):
        """Combines rendered page bytes into a single PDF file.

        Args:
            rendered_pages: Dictionary mapping 1-based page number to page bytes.
            total_pages: The total number of pages expected in the final PDF.
            output_path: The path to save the final combined PDF.
        """
        final_doc = fitz.open() # Create a new empty document
        added_pages_count = 0

        print(f"Combining {len(rendered_pages)} rendered pages into final PDF...")

        for page_num in range(1, total_pages + 1):
            page_bytes = rendered_pages.get(page_num)
            if page_bytes:
                try:
                    page_doc = fitz.open("pdf", page_bytes) # Load page bytes into a temp doc
                    final_doc.insert_pdf(page_doc) # Insert the page into the final doc
                    page_doc.close()
                    added_pages_count += 1
                except Exception as e:
                    print(f"Error inserting page {page_num} into final PDF: {e}. Skipping this page.")
            else:
                print(f"Warning: Rendered data for page {page_num} not found. Skipping this page in the final PDF.")
                # Optionally, could insert a blank page or the original page here

        if added_pages_count > 0:
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                final_doc.save(output_path, garbage=4, deflate=True)
                print(f"Successfully saved translated PDF ({added_pages_count}/{total_pages} pages) to: {output_path}")
            except Exception as e:
                print(f"Error saving final PDF to '{output_path}': {e}")
        else:
            print("No pages were successfully rendered or added. Final PDF not saved.")

        final_doc.close() 