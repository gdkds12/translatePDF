from PySide6.QtCore import QObject, Signal
import os
import csv
from typing import Dict, Any, Optional

# Import core components
from ..core.pdf_loader import PDFLoader
from ..core.doc_parser import AzureDocumentParser
from ..core.text_merger import TextBlockMerger
from ..core.translator import Translator
from ..core.layout_engine import LayoutEngine, register_font, DEFAULT_FONT_NAME, DEFAULT_FONT_PATH
from ..core.page_renderer import PageRenderer
from ..core.exporter import Exporter
from ..core.chunk_processor import ChunkProcessor

class UIController(QObject):
    """Handles the interaction between the GUI and the backend processing logic."""
    # Signal to update GUI progress: current_step, total_steps, status_message
    progress_signal = Signal(int, int, str)
    # Signal for completion: output_file_path or error string
    finished_signal = Signal(str)

    def __init__(self):
        super().__init__()
        
        # Initialize core components (defer layout engine until font known)
        self.pdf_loader = PDFLoader()
        self.doc_parser = AzureDocumentParser()
        self.text_merger = TextBlockMerger()
        self.translator = Translator() 
        self.layout_engine: Optional[LayoutEngine] = None # Initialize later
        self.page_renderer: Optional[PageRenderer] = None # Initialize later
        self.exporter = Exporter()
        self.chunk_processor: Optional[ChunkProcessor] = None # Initialize later
        self.total_chunks = 0

    def _initialize_processing_components(self, options: Dict[str, Any]):
        """Initializes components that depend on runtime options like font."""
        font_name = options.get("font_name", DEFAULT_FONT_NAME)
        font_path = options.get("font_path", DEFAULT_FONT_PATH)
        font_size = options.get("font_size", 10)
        
        # Register the font first
        resolved_font_name = register_font(font_name, font_path)
        
        # Now initialize/update components that need the font info
        if not self.layout_engine:
            self.layout_engine = LayoutEngine(font_name=resolved_font_name, font_path=font_path, default_font_size=font_size)
        else:
            self.layout_engine.update_paragraph_style(font_name=resolved_font_name, font_size=font_size)
        
        if not self.page_renderer:
            self.page_renderer = PageRenderer(self.layout_engine)
        # No need to re-init page_renderer if layout_engine instance remains the same

        if not self.chunk_processor:
             self.chunk_processor = ChunkProcessor(
                doc_parser=self.doc_parser,
                text_merger=self.text_merger,
                translator=self.translator,
                layout_engine=self.layout_engine,
                page_renderer=self.page_renderer
            )
        # Ensure chunk_processor uses the potentially updated translator/layout engine
        self.chunk_processor.translator = self.translator
        self.chunk_processor.layout_engine = self.layout_engine
        self.chunk_processor.page_renderer = self.page_renderer
        
        print(f"Processing components initialized/updated. Using font: {resolved_font_name}")

    def start_processing(self, pdf_path: str, output_dir: str, options: Dict[str, Any]) -> str:
        """Starts the PDF translation process (intended to be called by the background thread)."""
        try:
            print(f"Processing started for: {pdf_path} with options: {options}")
            base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
            output_filename = f"{base_filename}_translated.pdf"
            output_path = os.path.join(output_dir, output_filename)

            # --- Apply options --- 
            tone_map = {"격식체": "formal", "친근체": "friendly"}
            translate_tone = tone_map.get(options.get("tone", "격식체"), "formal")
            
            glossary = {}
            glossary_path = options.get("glossary_path")
            if glossary_path:
                glossary = self._load_glossary(glossary_path)
            
            # Update translator settings before initializing components that use it
            self.translator.update_settings(translate_tone=translate_tone, glossary=glossary)
            
            # Initialize/Update components like LayoutEngine with font info from options
            self._initialize_processing_components(options)

            # --- Processing Steps --- 
            # Estimate total steps for progress bar (1 load + N chunks + 1 save)
            
            # 1. Load and split PDF
            self.progress_signal.emit(0, 1, "PDF 로딩 및 청크 분할 중...") # Step 0 of N+1
            chunks, total_pages = self.pdf_loader.load_and_split(pdf_path)
            if not chunks:
                raise ValueError("PDF를 로드하거나 청크로 분할할 수 없습니다.")
            self.total_chunks = len(chunks)
            total_steps = 1 + self.total_chunks + 1 # Load + Chunks + Save

            # 2. Process chunks sequentially
            all_rendered_pages: Dict[int, bytes] = {}
            if self.chunk_processor is None:
                 raise RuntimeError("Chunk processor not initialized.") # Should not happen
                
            for i, chunk in enumerate(chunks):
                current_step = i + 1 # Step 1 to N
                status = f"청크 {i+1}/{self.total_chunks} 처리 중 (페이지 {chunk.page_numbers[0]}-{chunk.page_numbers[1]})..."
                self.progress_signal.emit(current_step, total_steps, status)
                
                rendered_chunk_pages = self.chunk_processor.process_chunk(pdf_path, chunk)
                all_rendered_pages.update(rendered_chunk_pages)
                
            # 3. Combine and save
            if not all_rendered_pages:
                 raise ValueError("번역 및 렌더링된 페이지가 없습니다.")
                 
            save_step = self.total_chunks + 1 # Step N+1
            self.progress_signal.emit(save_step, total_steps, f"최종 PDF 파일 저장 중... ({output_path})")
            self.exporter.save_pdf(all_rendered_pages, total_pages, output_path)

            self.progress_signal.emit(total_steps, total_steps, "번역 완료!")
            print(f"Processing finished. Output: {output_path}")
            return output_path 
            
        except Exception as e:
            print(f"Error during processing: {e}")
            # Ensure progress signal indicates failure if possible
            self.progress_signal.emit(0, 1, f"오류: {e}") # Reset progress, show error
            raise # Re-raise exception for the thread to catch

    def _load_glossary(self, path: str) -> Dict[str, str]:
        """Loads glossary from a CSV file (eng,kor)."""
        glossary_data = {}
        try:
            with open(path, mode='r', encoding='utf-8-sig') as csvfile: # utf-8-sig handles BOM
                reader = csv.reader(csvfile)
                # Skip header if present (optional)
                # next(reader, None) 
                for i, row in enumerate(reader):
                    if len(row) == 2:
                        eng, kor = row[0].strip(), row[1].strip()
                        if eng and kor:
                             glossary_data[eng] = kor
                        else:
                            print(f"Warning: Skipping empty entry in glossary row {i+1}")
                    elif row: # Non-empty row with wrong number of columns
                         print(f"Warning: Skipping malformed glossary row {i+1}: {row}")
            print(f"Loaded {len(glossary_data)} terms from glossary: {path}")
        except FileNotFoundError:
            print(f"Error: Glossary file not found at {path}")
        except Exception as e:
            print(f"Error reading glossary file {path}: {e}")
        return glossary_data

    def get_total_chunks(self) -> int:
         # This might be called before processing starts, return 0 or last value
         return self.total_chunks 