import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar, 
    QComboBox, QTextEdit, QGroupBox, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from .controller import UIController # Import controller

class ProcessingThread(QThread):
    """Worker thread for long-running PDF processing."""
    # Connect controller's signal to this thread's signal emitter
    # progress_updated = Signal(int, int, str) # current_step, total_steps, status_message
    processing_finished = Signal(str) # output_path or error message

    def __init__(self, controller: UIController, pdf_path: str, output_dir: str, options: dict):
        super().__init__()
        self.controller = controller 
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.options = options
        # Signal proxy: Connect controller's progress signal to the thread's signal
        # This allows the GUI to connect to the thread's signal directly
        # self.controller.progress_signal.connect(self.progress_updated.emit)

    # Re-declare the signal here if needed for direct connection in run()
    progress_updated = Signal(int, int, str)

    def run(self):
        """Runs the processing logic in the background."""
        try:
            # Connect controller signal to this thread's signal emitter *within the thread*
            # This ensures the signal is emitted correctly from the thread context
            self.controller.progress_signal.connect(self.progress_updated.emit)
            
            output_path = self.controller.start_processing(self.pdf_path, self.output_dir, self.options)
            self.processing_finished.emit(output_path)
        except Exception as e:
            # Ensure error message is emitted via the finished signal
            self.processing_finished.emit(f"Error: {e}")
        finally:
            # Disconnect signal when done to avoid issues if thread is reused (though it shouldn't be)
            try:
                 self.controller.progress_signal.disconnect(self.progress_updated.emit)
            except (RuntimeError, TypeError): # Ignore if already disconnected or errors
                 pass 

class MainGUI(QMainWindow):
    """Main application window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 번역기 (레이아웃 유지) v0.1")
        self.setGeometry(100, 100, 900, 700) # Increased size slightly

        self.controller: UIController | None = None 
        self.processing_thread: ProcessingThread | None = None
        self.selected_font_path: str | None = None # Store selected font path

        self._init_ui()

    def set_controller(self, controller: UIController):
        self.controller = controller

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- Left Panel (Input & Options) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        # File Input
        file_group = QGroupBox("파일 입력")
        file_layout = QVBoxLayout(file_group)
        self.file_path_edit = QLineEdit("선택된 파일 없음")
        self.file_path_edit.setReadOnly(True)
        browse_button = QPushButton("PDF 파일 선택...")
        browse_button.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(browse_button)
        left_layout.addWidget(file_group)

        # Options
        options_group = QGroupBox("번역 옵션")
        options_layout = QVBoxLayout(options_group)
        # Tone
        tone_layout = QHBoxLayout()
        tone_layout.addWidget(QLabel("번역 톤:"))
        self.tone_combo = QComboBox()
        self.tone_combo.addItems(["격식체", "친근체"])
        tone_layout.addWidget(self.tone_combo)
        options_layout.addLayout(tone_layout)
        
        # Glossary
        glossary_layout = QHBoxLayout()
        self.glossary_label = QLabel("Glossary: 없음")
        self.glossary_label.setWordWrap(True)
        browse_glossary_button = QPushButton("Glossary 선택 (.csv)")
        browse_glossary_button.clicked.connect(self._browse_glossary)
        glossary_layout.addWidget(self.glossary_label)
        glossary_layout.addWidget(browse_glossary_button)
        options_layout.addLayout(glossary_layout)
        self.glossary_path: str | None = None

        # Font Selection
        font_layout = QHBoxLayout()
        self.font_label = QLabel("글꼴: 기본") # Show selected font name/path
        self.font_label.setWordWrap(True)
        browse_font_button = QPushButton("글꼴 선택 (.ttf)")
        browse_font_button.clicked.connect(self._browse_font)
        font_layout.addWidget(self.font_label)
        font_layout.addWidget(browse_font_button)
        options_layout.addLayout(font_layout)

        left_layout.addWidget(options_group)
        
        # Output Path
        output_group = QGroupBox("출력 설정")
        output_layout = QVBoxLayout(output_group)
        self.output_path_edit = QLineEdit("출력 폴더 선택되지 않음")
        self.output_path_edit.setReadOnly(True)
        browse_output_button = QPushButton("출력 폴더 선택...")
        browse_output_button.clicked.connect(self._browse_output_dir)
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(browse_output_button)
        left_layout.addWidget(output_group)

        left_layout.addStretch(1) # Push button to bottom

        # Action Button
        self.start_button = QPushButton("번역 시작")
        self.start_button.setFixedHeight(40) # Make button larger
        self.start_button.clicked.connect(self._start_processing)
        left_layout.addWidget(self.start_button)

        # --- Right Panel (Progress & Log) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Progress Bar
        progress_group = QGroupBox("진행 상태")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.status_label = QLabel("대기 중...")
        self.status_label.setWordWrap(True)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        right_layout.addWidget(progress_group)

        # Log Area
        log_group = QGroupBox("로그")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        right_layout.addWidget(log_group)

        main_layout.addWidget(left_panel, 1) # Weight 1
        main_layout.addWidget(right_panel, 2) # Weight 2

    @Slot()
    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "PDF 파일 선택", "", "PDF Files (*.pdf)")
        if file_path:
            self.file_path_edit.setText(file_path)
            self._append_log(f"입력 파일: {file_path}")

    @Slot()
    def _browse_glossary(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Glossary 파일 선택", "", "CSV Files (*.csv)")
        if file_path:
            self.glossary_path = file_path
            self.glossary_label.setText(f"Glossary: {os.path.basename(file_path)}")
            self._append_log(f"Glossary 파일: {file_path}")
        else:
             self.glossary_path = None
             self.glossary_label.setText("Glossary: 없음")

    @Slot()
    def _browse_font(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "글꼴 파일 선택", "", "TrueType Fonts (*.ttf)")
        if file_path:
            self.selected_font_path = file_path
            # Try to get font name, fallback to filename
            font_name = os.path.splitext(os.path.basename(file_path))[0]
            self.font_label.setText(f"글꼴: {font_name}")
            self._append_log(f"글꼴 파일: {file_path}")
        else:
            self.selected_font_path = None
            self.font_label.setText("글꼴: 기본")

    @Slot()
    def _browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if dir_path:
            self.output_path_edit.setText(dir_path)
            self._append_log(f"출력 폴더: {dir_path}")

    @Slot()
    def _start_processing(self):
        pdf_path = self.file_path_edit.text()
        output_dir = self.output_path_edit.text()

        if not pdf_path or pdf_path == "선택된 파일 없음":
            self._append_log("오류: PDF 파일을 선택해주세요.")
            return
        if not output_dir or output_dir == "출력 폴더 선택되지 않음":
             self._append_log("오류: 출력 폴더를 선택해주세요.")
             return
        if not self.controller:
             self._append_log("오류: 내부 컨트롤러가 설정되지 않았습니다.")
             return
        if self.processing_thread and self.processing_thread.isRunning():
            self._append_log("오류: 이미 번역 작업이 진행 중입니다.")
            return

        options = {
            "tone": self.tone_combo.currentText(),
            "glossary_path": self.glossary_path, 
            "font_path": self.selected_font_path, # Can be None
            "font_name": os.path.splitext(os.path.basename(self.selected_font_path))[0] if self.selected_font_path else None,
            # "font_size": 10 # Could add font size option later
        }

        self._append_log("-" * 30)
        self._append_log("번역 작업을 시작합니다...")
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100) # Reset max value potentially
        self.status_label.setText("처리 시작...")

        # Create and start the processing thread
        self.processing_thread = ProcessingThread(self.controller, pdf_path, output_dir, options)
        # Connect signals from the thread to GUI slots
        self.processing_thread.progress_updated.connect(self.update_progress)
        self.processing_thread.processing_finished.connect(self._processing_finished)
        self.processing_thread.start()

    @Slot(int, int, str)
    def update_progress(self, current_step: int, total_steps: int, status_message: str):
        """Updates the progress bar and status label."""
        if total_steps > 0:
             progress_percent = int((current_step / total_steps) * 100)
        else: # Avoid division by zero if total_steps is somehow 0
             progress_percent = 0
             
        self.progress_bar.setValue(progress_percent)
        self.progress_bar.setFormat(f"%p% ({current_step}/{total_steps})")
        self.status_label.setText(status_message)
        # Only log significant status changes to avoid flooding the log
        if "청크" in status_message or "저장 중" in status_message or "완료" in status_message or "오류" in status_message or "로딩" in status_message:
             self._append_log(f"진행: {status_message}")

    @Slot(str)
    def _processing_finished(self, result_message: str):
        """Called when the processing thread finishes."""
        if result_message.startswith("Error:"):
            self.status_label.setText("오류 발생")
            self.progress_bar.setValue(0) # Reset progress on error
            self.progress_bar.setFormat("오류")
            self._append_log(f"번역 실패: {result_message}")
        else:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("완료")
            self.status_label.setText("번역 완료")
            self._append_log(f"번역 완료! 결과 파일: {result_message}")
            self._append_log("=" * 30)
        
        self.start_button.setEnabled(True)
        self.processing_thread = None # Clear the thread reference

    def _append_log(self, message: str):
        """Appends a message to the log text area."""
        self.log_edit.append(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum()) # Auto-scroll

# Main execution block (usually in main.py)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     controller = UIController()
#     window = MainGUI()
#     window.set_controller(controller)
#     window.show()
#     sys.exit(app.exec()) 