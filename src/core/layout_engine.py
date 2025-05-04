import fitz # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4 # Or use original page size
from reportlab.lib import units # Import the units module
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT # Text Alignment
from reportlab.lib import colors # Import colors module
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
            fontName=self.font_name,
            fontSize=self.default_font_size,
            textColor=colors.black,
            leading=self.default_font_size * 1.2, # Line spacing
            alignment=TA_LEFT,
        )
        print(f"LayoutEngine style updated: Font='{self.font_name}', Size={self.default_font_size}")

    def _embed_font(self, canvas_obj):
        """글꼴을 PDF에 명시적으로 임베딩합니다."""
        try:
            # PDF에 사용할 폰트를 문서에 등록
            canvas_obj.setFont(self.font_name, self.default_font_size)
            print(f"  Font '{self.font_name}' set for PDF document")
        except Exception as e:
            print(f"  Warning: Could not explicitly embed font: {e}")

    def overlay_text_on_page(self, original_pdf_path: str, page_num: int, translated_blocks: List[TranslatedBlock]) -> Optional[bytes]:
        """Renders the original page and overlays translated text."""
        print(f"[LayoutEngine] Starting overlay for page {page_num} with {len(translated_blocks)} blocks.")
        try:
            # 1단계: 원본 PDF 열기
            original_doc = fitz.open(original_pdf_path)
            if page_num <= 0 or page_num > len(original_doc):
                print(f"Error: Page number {page_num} is out of range (1-{len(original_doc)}).")
                original_doc.close()
                return None
            
            # 원본 페이지 정보 가져오기
            original_page = original_doc.load_page(page_num - 1)
            
            # --- 원본 텍스트 가리기 (Redaction 재시도) ---
            print(f"  Applying redactions to cover original text areas for page {page_num}...")
            redactions_applied = 0
            POINTS_PER_INCH = 72.0
            # 먼저 모든 redaction annotation 추가
            for block in translated_blocks:
                if block.page_number == page_num:
                    bbox_x_pt = block.bbox.x * POINTS_PER_INCH
                    bbox_y_pt = block.bbox.y * POINTS_PER_INCH
                    bbox_width_pt = max(1.0, block.bbox.width * POINTS_PER_INCH)
                    bbox_height_pt = max(1.0, block.bbox.height * POINTS_PER_INCH)
                    margin = 1.0 # 약간의 여백 추가
                    redact_rect = fitz.Rect(bbox_x_pt - margin, 
                                            bbox_y_pt - margin, 
                                            bbox_x_pt + bbox_width_pt + margin, 
                                            bbox_y_pt + bbox_height_pt + margin)
                    try:
                        # cross_out=False 옵션 추가 (취소선 제거)
                        original_page.add_redact_annot(redact_rect, fill=(1, 1, 1), cross_out=False) 
                        redactions_applied += 1
                    except Exception as redact_err:
                         print(f"  Warning: Failed to add redaction for block {block.id}: {redact_err}")
                         
            # 모든 annotation 추가 후 한번에 적용 (이미지 보존)
            if redactions_applied > 0:
                try:
                    # images=0 또는 fitz.PDF_REDACT_IMAGE_NONE : 이미지 제거 안 함
                    original_page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE) 
                    print(f"  Applied {redactions_applied} redactions without removing images.")
                except Exception as apply_err:
                     print(f"  Warning: Failed to apply redactions: {apply_err}")
                     # 실패 시 원본 페이지를 계속 사용
            # ------------------------------------
            
            # 이제 수정된 페이지에서 크기 및 이미지 가져오기
            page_rect = original_page.rect
            page_width, page_height = page_rect.width, page_rect.height
            
            print(f"  Page dimensions: {page_width}x{page_height} pts")
            
            # 2단계: 직접 새 PDF 문서 생성
            output_buffer = BytesIO()
            c = canvas.Canvas(output_buffer, pagesize=(page_width, page_height))
            
            # 3단계: 원본 페이지를 고해상도로 이미지 추출 및 삽입
            # 고해상도로 인한 메모리 문제 완화를 위해 2.0으로 조정
            pix = original_page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            
            img_data = pix.tobytes("png")
            img_io = BytesIO(img_data)
            
            # ReportLab에 이미지 삽입
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(img_io)
                c.drawImage(img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
                print(f"  Successfully added high-resolution page background image ({len(img_data)} bytes)")
            except Exception as img_err:
                print(f"  Warning: Failed to add background image: {img_err}")
                # 이미지 삽입 실패해도 계속 진행
                
            # 글꼴을 명시적으로 임베딩
            self._embed_font(c)
            
            # 4단계: 번역된 텍스트 블록 추가
            blocks_added = 0
            for block in translated_blocks:
                if block.page_number == page_num:
                    try:
                        # 블록을 그리기 전에 글꼴 설정 확인
                        if self.font_name not in pdfmetrics.getRegisteredFontNames():
                            print(f"  Warning: Font '{self.font_name}' not registered, falling back to default")
                            self.paragraph_style.fontName = "Helvetica"
                        
                        self._draw_text_in_bbox(c, block.translated_text, block.bbox, 
                                               page_width, page_height, self.paragraph_style)
                        blocks_added += 1
                    except Exception as block_err:
                        print(f"  Warning: Failed to draw block {block.id}: {block_err}")
            
            print(f"  Added {blocks_added} text blocks")
            
            # 5단계: ReportLab PDF 생성 완료 (한글 임베딩 확인)
            c.showPage()  # 현재 페이지 완료
            c.save()
            output_buffer.seek(0)
            
            # PDF 검증 (디버깅용)
            print(f"  PDF generation complete: Buffer size {len(output_buffer.getvalue())} bytes")
            
            # 메모리 정리
            original_doc.close()
            
            pdf_bytes = output_buffer.getvalue()
            print(f"[LayoutEngine] Finished overlay for page {page_num}. Output size: {len(pdf_bytes)} bytes with font embedding.")
            return pdf_bytes
            
        except Exception as e:
            import traceback
            print(f"Error overlaying text on page {page_num}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            
            # 열려 있을 수 있는 문서 닫기
            if 'original_doc' in locals() and original_doc:
                try:
                    original_doc.close()
                except:
                    pass
            
            return None

    def _draw_text_in_bbox(self, canvas: canvas.Canvas, text: str, 
                             bbox: BoundingBox, page_width: float, page_height: float,
                             style: ParagraphStyle):
        """Draws text within the specified bounding box using ReportLab Paragraph.
           Handles text wrapping automatically.
           Assumes bbox coordinates are in INCHES (from DI for PDF) and page dimensions are in POINTS (from fitz).
        """
        # print(f"  [LayoutEngine._draw] BBox IN (inches): ({bbox.x:.2f},{bbox.y:.2f}, w:{bbox.width:.2f}, h:{bbox.height:.2f})\") # Debug Input
        
        # page_width, page_height are already in points
        POINTS_PER_INCH = 72.0

        # Convert bbox from inches to points
        bbox_x_pt = bbox.x * POINTS_PER_INCH
        bbox_y_pt = bbox.y * POINTS_PER_INCH
        bbox_width_pt = max(1.0, bbox.width * POINTS_PER_INCH)  # Min width 1pt
        bbox_height_pt = max(1.0, bbox.height * POINTS_PER_INCH) # Min height 1pt

        frame_x = bbox_x_pt
        # ReportLab Y starts from bottom, DI Y starts from top
        frame_y = page_height - (bbox_y_pt + bbox_height_pt)

        # Debug log using point values
        print(f"    [Draw] Text='{text[:20]}...' Font='{style.fontName}' Size={style.fontSize:.1f} Frame=({frame_x:.1f},{frame_y:.1f}, w:{bbox_width_pt:.1f}, h:{bbox_height_pt:.1f}) PageH={page_height:.1f}")
        
        try:
            # 1. Prepare Paragraph and Frame
            text_html = text.replace('\n', '<br/>')
            paragraph = Paragraph(text_html, style)
            print(f"      [Para] Created Paragraph: Text='{text[:30].replace('<br/>', ' ')}...' Font='{paragraph.style.fontName}' Size={paragraph.style.fontSize} Color={paragraph.style.textColor}")
 
            # --- Direct Paragraph Drawing (DEBUGGING) ---
            print(f"      [Draw] Attempting paragraph.drawOn({frame_x:.1f}, {frame_y:.1f})...")
            # **중요**: drawOn 전에 wrapOn을 호출하여 Paragraph 내부 구조 초기화
            availWidth = bbox_width_pt
            availHeight = bbox_height_pt # 사용 가능한 높이 (무한대로 설정할 수도 있음)
            w, h = paragraph.wrapOn(canvas, availWidth, availHeight)
            print(f"      [ParaWrap] Wrapped size: ({w:.1f}, {h:.1f}) vs BBox size: ({bbox_width_pt:.1f}, {bbox_height_pt:.1f})")
            
            # wrapOn 이후에 drawOn 호출
            paragraph.drawOn(canvas, frame_x, frame_y)
            print(f"      [Draw] Successfully called paragraph.drawOn.")
            # -------------------------------------------

        except Exception as e_draw:
             import traceback
             print(f"    ERROR drawing paragraph '{text[:20]}...' in frame (x={frame_x:.1f}, y={frame_y:.1f}, w={bbox_width_pt:.1f}, h={bbox_height_pt:.1f}): {e_draw}")
             print(traceback.format_exc()) # 전체 Traceback 출력

        # --- Debug: Draw the BBox outline manually ---
        canvas.saveState()
        canvas.setStrokeColor(colors.blue) # Use blue for the manual box
        canvas.setLineWidth(0.5)
        canvas.rect(frame_x, frame_y, bbox_width_pt, bbox_height_pt, stroke=1, fill=0)
        canvas.restoreState() 