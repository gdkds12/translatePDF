import sys
from PySide6.QtWidgets import QApplication
from src.gui.main_window import MainGUI
from src.gui.controller import UIController
from src.config import validate_config # Ensure config loads early

def main():
    """Main application entry point."""
    # Ensure environment variables are loaded and validated
    try:
        validate_config()
        # You might want stricter checks here, e.g., raising errors in validate_config
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Please check your .env file.")
        sys.exit(1)
    except Exception as e:
         print(f"An unexpected error occurred during configuration: {e}")
         sys.exit(1)

    app = QApplication(sys.argv)

    # Initialize components
    controller = UIController()
    window = MainGUI()
    window.set_controller(controller) # Inject controller into GUI

    # Connect controller signals to GUI slots for progress updates
    # Note: The ProcessingThread already connects to the GUI slots directly
    # If controller needs to emit signals *outside* the thread context, connect here.
    # controller.progress_signal.connect(window.update_progress)
    # controller.finished_signal.connect(window._processing_finished) 

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 