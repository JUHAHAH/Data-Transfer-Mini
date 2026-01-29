"""
GUI entry point for MySQL Data Parser and Transmitter.
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from gui import MainWindow


def main(config_path: str = "config.json"):
    """Launch GUI application."""
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("MySQL Data Parser")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Data Parser")
    
    # Create and show main window
    window = MainWindow(config_path=config_path)
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='MySQL Data Parser GUI')
    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    
    args = parser.parse_args()
    main(config_path=args.config)
