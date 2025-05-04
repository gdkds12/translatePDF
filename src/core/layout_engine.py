import fitz # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4 # Or use original page size
from reportlab.lib.units import pt
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT # Text Alignment
from io import BytesIO
from typing import List, Optional
from ..models import TranslatedBlock, BoundingBox
import os

# --- Font Management --- 
registered_fonts = set()
fallback_font_name = "Helvetica"

def register_font(font_name: str, font_path: str) -> str:
    """Registers a TTF font with ReportLab if not already registered."""
    global fallback_font_name
    if font_name in registered_fonts:
        return font_name
    
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            registered_fonts.add(font_name)
            print(f"Successfully registered font '{font_name}' from '{font_path}'")
            return font_name
        except Exception as e:
            print(f"Warning: Could not register font '{font_name}' from '{font_path}': {e}")
            return fallback_font_name
    else:
        print(f"Warning: Font file not found at '{font_path}'. Using fallback {fallback_font_name}.")
        return fallback_font_name

# --- Default Font (Example: Malgun Gothic on Windows) ---
# This should be configurable via GUI
DEFAULT_FONT_PATH = "C:/Windows/Fonts/malgun.ttf" 
DEFAULT_FONT_NAME = "MalgunGothic"

# Register default font on module load
fallback_font_name = register_font(DEFAULT_FONT_NAME, DEFAULT_FONT_PATH)
if DEFAULT_FONT_NAME not in registered_fonts:
     DEFAULT_FONT_NAME = fallback_font_name # Update default if registration failed

class LayoutEngine:
    """Overlays translated text onto the original PDF page locations."""

    def __init__(self, font_name: str = DEFAULT_FONT_NAME, 
                 font_path: str = DEFAULT_FONT_PATH, 
                 default_font_size: int = 10):
        # Attempt to register the specified font
        self.font_name = register_font(font_name, font_path)
        self.default_font_size = default_font_size
        # Create default style
        self.styles = getSampleStyleSheet()
        self.update_paragraph_style() # Set initial style
        
    def update_paragraph_style(self, font_name: Optional[str] = None, font_size: Optional[int] = None):
        """Updates the paragraph style used for drawing text."""
        if font_name:
            # Assuming font is already registered if passed here
            self.font_name = font_name 
        if font_size:
            self.default_font_size = font_size
            
        # Ensure the font name exists in pdfmetrics before creating style
        if self.font_name not in pdfmetrics.getRegisteredFontNames():
             print(f"Error: Font '{self.font_name}' not registered. Falling back to {fallback_font_name}.")
             self.font_name = fallback_font_name
        
        self.paragraph_style = ParagraphStyle(
            name='TranslatedTextStyle',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=self.default_font_size,
            leading=self.default_font_size * 1.2, # Line spacing
            alignment=TA_LEFT,
        )
        print(f"LayoutEngine style updated: Font='{self.font_name}', Size={self.default_font_size}")

    def overlay_text_on_page(self, original_pdf_path: str, page_num: int, translated_blocks: List[TranslatedBlock]) -> Optional[bytes]:
        """Renders the original page and overlays translated text.
        (Code for merging overlay with original page remains the same)
        """
        try:
            original_doc = fitz.open(original_pdf_path)
            if page_num <= 0 or page_num > len(original_doc):
                print(f"Error: Page number {page_num} is out of range.")
                original_doc.close()
                return None

            original_page = original_doc.load_page(page_num - 1)
            page_rect = original_page.rect
            page_width, page_height = page_rect.width, page_rect.height

            packet = BytesIO()
            # Use page dimensions from original PDF
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            # Draw translated text blocks using Paragraph for wrapping
            for block in translated_blocks:
                if block.page_number == page_num:
                    # Use the updated style
                    self._draw_text_in_bbox(can, block.translated_text, block.bbox, 
                                            page_width, page_height, self.paragraph_style)

            can.save()
            packet.seek(0)
            overlay_pdf_bytes = packet.read()
            original_doc.close()

            # Merge overlay onto original page (same logic as before)
            overlay_doc = fitz.open("pdf", overlay_pdf_bytes)
            if not overlay_doc or len(overlay_doc) == 0:
                 print(f"Error: Failed to create overlay PDF for page {page_num}.")
                 return None
            
            # Open the original again to merge
            final_doc = fitz.open() 
            temp_orig_doc = fitz.open(original_pdf_path)
            final_page = final_doc.new_page(width=page_width, height=page_height)
            
            # Draw original page content first
            final_page.show_pdf_page(original_page.rect, temp_orig_doc, page_num - 1)
            # Then, overlay the translated text layer
            final_page.show_pdf_page(overlay_doc[0].rect, overlay_doc, 0)
            
            temp_orig_doc.close()
            overlay_doc.close()
            
            # Save the merged page to bytes
            final_page_bytes = final_doc.tobytes(garbage=4, deflate=True)
            final_doc.close()
            
            return final_page_bytes

        except Exception as e:
            print(f"Error overlaying text on page {page_num}: {e}")
            # Clean up open documents
            if 'original_doc' in locals() and original_doc.is_open:
                original_doc.close()
            if 'overlay_doc' in locals() and overlay_doc.is_open:
                overlay_doc.close()
            if 'temp_orig_doc' in locals() and temp_orig_doc.is_open:
                 temp_orig_doc.close()
            if 'final_doc' in locals() and final_doc.is_open:
                final_doc.close()
            return None

    def _draw_text_in_bbox(self, canvas: canvas.Canvas, text: str, 
                             bbox: BoundingBox, page_width: float, page_height: float,
                             style: ParagraphStyle):
        """Draws text within the specified bounding box using ReportLab Paragraph.
           Handles text wrapping automatically.
        """
        # DI BBox (top-left origin, dimensions) to ReportLab Frame coords (bottom-left origin)
        # Convert dimensions from potentially abstract DI units to points (1/72 inch)
        # Assuming DI units are close enough to points for now. ADJUST if DI provides unit info.
        frame_width = bbox.width * pt 
        frame_height = bbox.height * pt
        frame_x = bbox.x * pt
        # ReportLab Y starts from bottom, DI Y starts from top
        frame_y = (page_height - (bbox.y + bbox.height)) * pt

        # Replace newlines in text with <br/> tags for Paragraph
        text_html = text.replace('\n', '<br/>')
        
        # Create Paragraph
        paragraph = Paragraph(text_html, style)

        # Create a Frame to hold the Paragraph and constrain it
        frame = Frame(
            frame_x,
            frame_y,
            frame_width,
            frame_height,
            leftPadding=1, # Small padding
            bottomPadding=1,
            rightPadding=1,
            topPadding=1,
            showBoundary=0 # Set to 1 for debugging bbox
        )

        # Draw the paragraph within the frame on the canvas
        # This handles wrapping automatically.
        # TODO: Implement font size reduction if text overflows frame height.
        # This requires calculating the paragraph height and comparing to frame_height.
        # wrapped_width, wrapped_height = paragraph.wrapOn(canvas, frame_width, frame_height)
        # if wrapped_height > frame_height:
            # Logic to reduce font size in style and retry wrapping/drawing
        
        frame.addFromList([paragraph], canvas)

        # --- Debug: Draw the BBox outline ---
        # canvas.saveState()
        # canvas.setStrokeColorRGB(1, 0, 0) # Red
        # canvas.rect(frame_x, frame_y, frame_width, frame_height, stroke=1, fill=0)
        # canvas.restoreState() 