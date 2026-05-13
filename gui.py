"""
GUI module for MySQL Data Parser and Transmitter.
"""
import sys
import json
import logging
from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QLineEdit, QSpinBox, QTextEdit, QPlainTextEdit, QListWidget,
    QListWidgetItem, QGroupBox, QFormLayout, QMessageBox, QDialog,
    QDialogButtonBox, QCheckBox, QComboBox, QScrollArea, QSplitter
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QObject
from PySide6.QtGui import QTextCharFormat, QColor, QFont

from config import Config, ConfigError
from database import Database, DatabaseError
from main import DataParserApp


class GUILogHandler(logging.Handler, QObject):
    """Custom log handler that emits Qt signals for GUI updates."""
    
    log_message = Signal(str, str)  # message, level
    
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    def emit(self, record):
        """Emit log record as signal."""
        try:
            msg = self.format(record)
            level = record.levelname
            self.log_message.emit(msg, level)
        except Exception:
            self.handleError(record)


class MonitoringThread(QThread):
    """Thread for running the monitoring loop."""
    
    status_update = Signal(dict)
    error_occurred = Signal(str)
    
    def __init__(self, app: DataParserApp):
        super().__init__()
        self.app = app
        self._stop_requested = False
    
    def run(self):
        """Run the monitoring loop."""
        import schedule
        import time
        try:
            while self.app.running and not self._stop_requested:
                schedule.run_pending()
                # Emit status update every second
                status = self.app.get_status()
                self.status_update.emit(status)
                time.sleep(1)  # Check every second for scheduled tasks
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop(self):
        """Request thread to stop."""
        self._stop_requested = True
        if self.app:
            self.app.stop_monitoring()


class LogConsole(QTextEdit):
    """Custom text widget for displaying logs with color coding."""
    
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        
        # Define colors for different log levels
        self.colors = {
            'INFO': QColor(0, 0, 0),
            'WARNING': QColor(255, 165, 0),
            'ERROR': QColor(255, 0, 0),
            'DEBUG': QColor(128, 128, 128),
            'CRITICAL': QColor(255, 0, 0)
        }
    
    def append_log(self, message: str, level: str = 'INFO'):
        """Append a log message with appropriate color."""
        color = self.colors.get(level, QColor(0, 0, 0))
        
        format = QTextCharFormat()
        format.setForeground(color)
        
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.setCharFormat(format)
        cursor.insertText(message + '\n')
        
        # Auto-scroll to bottom
        self.ensureCursorVisible()


class ProgramRunTab(QWidget):
    """Tab for program run controls and log console."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app: Optional[DataParserApp] = None
        self.monitoring_thread: Optional[MonitoringThread] = None
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_monitoring_after_error)
        self._restart_error_series = 0
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout()
        
        # Control panel
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()
        
        # Start/Stop buttons
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.clicked.connect(self.start_monitoring)
        self.stop_btn = QPushButton("Stop Monitoring")
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.stop_btn.setEnabled(False)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addStretch()
        
        control_layout.addLayout(button_layout)
        
        # Status and interval
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Stopped")
        self.interval_label = QLabel("Interval (seconds):")
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimum(1)
        self.interval_spinbox.setMaximum(3600)
        self.interval_spinbox.setValue(60)
        self.interval_spinbox.valueChanged.connect(self.on_interval_changed)
        
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.interval_label)
        status_layout.addWidget(self.interval_spinbox)
        
        control_layout.addLayout(status_layout)
        
        # Last processed ID
        self.last_id_label = QLabel("Last Processed ID: N/A")
        control_layout.addWidget(self.last_id_label)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Log console
        log_group = QGroupBox("Log Console")
        log_layout = QVBoxLayout()
        self.log_console = LogConsole()
        log_layout.addWidget(self.log_console)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.setLayout(layout)
    
    def set_app(self, app: DataParserApp):
        """Set the application instance."""
        self.app = app
        if app and app.config:
            self.interval_spinbox.setValue(int(app.config.interval_seconds))

    def set_config(self, config: Optional[Config]):
        """Set config reference for persisting interval when app not yet started."""
        self._config = config
        if config:
            self.interval_spinbox.setValue(int(config.interval_seconds))
    
    def start_monitoring(self):
        """Start monitoring."""
        if not self.app:
            QMessageBox.warning(self, "Error", "Application not initialized")
            return
        
        try:
            # Initialize if needed
            if not self.app.config:
                self.app.initialize()
            
            # Start monitoring
            self.app.start_monitoring()
            
            # Start monitoring thread
            self.monitoring_thread = MonitoringThread(self.app)
            self.monitoring_thread.status_update.connect(self.on_status_update)
            self.monitoring_thread.error_occurred.connect(self.on_error)
            self.monitoring_thread.start()
            
            # Update UI
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("Status: Running")
            self.status_timer.start(1000)  # Update every second
            
            self.log_console.append_log("Monitoring started", "INFO")
            self._restart_error_series = 0
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start monitoring: {e}")
            self.log_console.append_log(f"Error starting monitoring: {e}", "ERROR")
    
    def _active_config(self) -> Optional[Config]:
        return getattr(self, '_config', None) or (self.app.config if self.app else None)
    
    def _restart_monitoring_after_error(self):
        """Called by timer to resume monitoring after a processing error."""
        if not self.app:
            return
        self.log_console.append_log("Auto-restart: starting monitoring...", "INFO")
        self.start_monitoring()
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self._restart_timer.stop()
        if self.monitoring_thread:
            self.monitoring_thread.stop()
            self.monitoring_thread.wait()
            self.monitoring_thread = None
        
        if self.app:
            self.app.stop_monitoring()
        
        # Update UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Status: Stopped")
        self.status_timer.stop()
        
        self.log_console.append_log("Monitoring stopped", "INFO")
    
    def on_interval_changed(self, value: int):
        """Handle interval change."""
        try:
            config = getattr(self, '_config', None) or (self.app.config if self.app else None)
            if self.app and self.app.running:
                self.app.set_interval(float(value))
                self.log_console.append_log(f"Interval updated to {value} seconds", "INFO")
            if config:
                config.update_interval(float(value))
                config.save()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to update interval: {e}")
    
    def on_status_update(self, status: dict):
        """Handle status update from monitoring thread."""
        if status.get('last_processed_id') is not None:
            self.last_id_label.setText(f"Last Processed ID: {status['last_processed_id']}")
    
    def on_error(self, error_msg: str):
        """Handle error from monitoring thread: stop monitoring, log, optional auto-restart."""
        self.log_console.append_log(f"Error: {error_msg}", "ERROR")
        self.log_console.append_log("Monitoring stopped due to error.", "ERROR")
        self.stop_monitoring()
        cfg = self._active_config()
        if cfg and cfg.monitoring_restart_on_error:
            self._restart_error_series += 1
            max_a = cfg.monitoring_restart_max_attempts
            if max_a > 0 and self._restart_error_series > max_a:
                self.log_console.append_log(
                    f"Auto-restart: gave up after {max_a} consecutive error(s).", "ERROR"
                )
                self._restart_error_series = 0
                QMessageBox.critical(
                    self, "Monitoring Error",
                    f"Monitoring stopped due to error.\n\n{error_msg}\n\n"
                    f"Auto-restart limit ({max_a}) reached."
                )
                return
            delay_sec = cfg.monitoring_restart_delay_seconds
            self.log_console.append_log(
                f"Auto-restart: monitoring will start again in {delay_sec:.0f} seconds.", "WARNING"
            )
            self._restart_timer.start(int(max(1.0, delay_sec) * 1000))
            return
        QMessageBox.critical(
            self, "Monitoring Error",
            f"Monitoring stopped due to error.\n\n{error_msg}"
        )
    
    def update_status(self):
        """Update status display."""
        if self.app:
            status = self.app.get_status()
            if status.get('last_processed_id') is not None:
                self.last_id_label.setText(f"Last Processed ID: {status['last_processed_id']}")
    
    def add_log_handler(self, handler: GUILogHandler):
        """Add log handler to capture logs."""
        handler.log_message.connect(self.log_console.append_log)
        logging.getLogger().addHandler(handler)


class DBConfigTab(QWidget):
    """Tab for database configuration."""
    
    config_saved = Signal()  # Signal emitted when config is saved
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config: Optional[Config] = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout()
        
        # Database configuration form
        form_group = QGroupBox("Database Configuration")
        form_layout = QFormLayout()
        
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost")
        form_layout.addRow("Host:", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setMinimum(1)
        self.port_input.setMaximum(65535)
        self.port_input.setValue(3306)
        form_layout.addRow("Port:", self.port_input)
        
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("username")
        form_layout.addRow("User:", self.user_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("password")
        
        # Show/hide password toggle
        password_layout = QHBoxLayout()
        password_layout.addWidget(self.password_input)
        self.show_password_btn = QPushButton("Show")
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.toggled.connect(self.toggle_password_visibility)
        password_layout.addWidget(self.show_password_btn)
        form_layout.addRow("Password:", password_layout)
        
        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("dbname")
        form_layout.addRow("Database:", self.database_input)
        
        self.table_input = QLineEdit()
        self.table_input.setPlaceholderText("tablename")
        form_layout.addRow("Table:", self.table_input)
        
        self.id_column_input = QLineEdit()
        self.id_column_input.setPlaceholderText("id")
        form_layout.addRow("ID Column:", self.id_column_input)
        
        self.query_input = QPlainTextEdit()
        self.query_input.setPlaceholderText("Optional: custom SQL (e.g. JOIN). Use exactly one %s for cursor. Leave empty to use table + ID column.")
        self.query_input.setMaximumHeight(100)
        form_layout.addRow("Custom query (optional):", self.query_input)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Test connection button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        self.connection_status_label = QLabel("")
        test_layout.addWidget(self.test_btn)
        test_layout.addWidget(self.connection_status_label)
        test_layout.addStretch()
        layout.addLayout(test_layout)
        
        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.clicked.connect(self.save_config)
        save_layout.addWidget(self.save_btn)
        layout.addLayout(save_layout)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def toggle_password_visibility(self, checked: bool):
        """Toggle password visibility."""
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_password_btn.setText("Hide")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_password_btn.setText("Show")
    
    def set_config(self, config: Config):
        """Load configuration into form."""
        self.config = config
        if config:
            db_config = config.database
            self.host_input.setText(db_config.get('host', ''))
            self.port_input.setValue(db_config.get('port', 3306))
            self.user_input.setText(db_config.get('user', ''))
            self.password_input.setText(db_config.get('password', ''))
            self.database_input.setText(db_config.get('database', ''))
            self.table_input.setText(db_config.get('table', ''))
            self.id_column_input.setText(db_config.get('id_column', ''))
            self.query_input.setPlainText(db_config.get('query', '') or '')
    
    def test_connection(self):
        """Test database connection."""
        try:
            db_config = {
                'host': self.host_input.text() or 'localhost',
                'port': self.port_input.value(),
                'user': self.user_input.text() or 'username',
                'password': self.password_input.text() or 'password',
                'database': self.database_input.text() or 'dbname',
                'table': self.table_input.text() or 'tablename',
                'id_column': self.id_column_input.text() or 'id'
            }
            
            db = Database(db_config)
            if db.test_connection():
                self.connection_status_label.setText("✓ Connection successful")
                self.connection_status_label.setStyleSheet("color: green;")
                QMessageBox.information(self, "Success", "Database connection successful!")
            else:
                self.connection_status_label.setText("✗ Connection failed")
                self.connection_status_label.setStyleSheet("color: red;")
                QMessageBox.warning(self, "Failed", "Database connection test failed")
        except Exception as e:
            self.connection_status_label.setText("✗ Error: " + str(e))
            self.connection_status_label.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Error", f"Connection error: {e}")
    
    def save_config(self):
        """Save configuration."""
        if not self.config:
            QMessageBox.warning(self, "Error", "No configuration loaded")
            return
        
        try:
            query_val = self.query_input.toPlainText().strip() or None
            self.config.update_database_config(
                host=self.host_input.text() or 'localhost',
                port=self.port_input.value(),
                user=self.user_input.text() or 'username',
                password=self.password_input.text() or 'password',
                database=self.database_input.text() or 'dbname',
                table=self.table_input.text() or 'tablename',
                id_column=self.id_column_input.text() or 'id',
                query=query_val
            )
            self.config.save()
            QMessageBox.information(self, "Success", "Configuration saved successfully!")
            # Notify parent to reload config
            if hasattr(self.parent(), 'reload_config'):
                self.parent().reload_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")


class ActionDialog(QDialog):
    """Dialog for editing action configuration."""
    
    def __init__(self, action_type: str, action_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.action_type = action_type
        self.action_data = action_data or {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize dialog UI."""
        self.setWindowTitle(f"Edit {self.action_type.upper()} Action")
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        if self.action_type == 'api':
            self.url_input = QLineEdit(self.action_data.get('url', ''))
            form_layout.addRow("URL:", self.url_input)
            
            self.method_combo = QComboBox()
            self.method_combo.addItems(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
            self.method_combo.setCurrentText(self.action_data.get('method', 'POST'))
            form_layout.addRow("Method:", self.method_combo)
            
            self.headers_input = QTextEdit()
            headers = self.action_data.get('headers', {})
            self.headers_input.setPlainText(json.dumps(headers, indent=2))
            form_layout.addRow("Headers (JSON):", self.headers_input)
            
            self.timeout_input = QSpinBox()
            self.timeout_input.setMinimum(1)
            self.timeout_input.setMaximum(300)
            self.timeout_input.setValue(self.action_data.get('timeout', 30))
            form_layout.addRow("Timeout (seconds):", self.timeout_input)
            
            self.retries_input = QSpinBox()
            self.retries_input.setMinimum(1)
            self.retries_input.setMaximum(10)
            self.retries_input.setValue(self.action_data.get('max_retries', 3))
            form_layout.addRow("Max Retries:", self.retries_input)
        
        elif self.action_type == 'file':
            self.path_input = QLineEdit(self.action_data.get('path', ''))
            form_layout.addRow("Path:", self.path_input)
            
            self.format_combo = QComboBox()
            self.format_combo.addItems(['json', 'csv', 'custom', 'structured'])
            self.format_combo.setCurrentText(self.action_data.get('format', 'json'))
            self.format_combo.currentTextChanged.connect(self.on_format_changed)
            form_layout.addRow("Format:", self.format_combo)
            
            self.structure_input = QTextEdit()
            structure = self.action_data.get('structure', {})
            self.structure_input.setPlainText(json.dumps(structure, indent=2))
            form_layout.addRow("Structure (JSON):", self.structure_input)
        
        elif self.action_type == 'ftp':
            self.ftp_host_input = QLineEdit(self.action_data.get('host', ''))
            form_layout.addRow("Host:", self.ftp_host_input)
            
            self.ftp_port_input = QSpinBox()
            self.ftp_port_input.setMinimum(1)
            self.ftp_port_input.setMaximum(65535)
            self.ftp_port_input.setValue(self.action_data.get('port', 21))
            form_layout.addRow("Port:", self.ftp_port_input)
            
            self.ftp_user_input = QLineEdit(self.action_data.get('user', ''))
            form_layout.addRow("User:", self.ftp_user_input)
            
            self.ftp_password_input = QLineEdit(self.action_data.get('password', ''))
            self.ftp_password_input.setEchoMode(QLineEdit.EchoMode.Password)
            form_layout.addRow("Password:", self.ftp_password_input)
            
            self.remote_path_input = QLineEdit(self.action_data.get('remote_path', '/'))
            form_layout.addRow("Remote Path:", self.remote_path_input)
            
            self.use_tls_checkbox = QCheckBox()
            self.use_tls_checkbox.setChecked(self.action_data.get('use_tls', False))
            form_layout.addRow("Use TLS:", self.use_tls_checkbox)
            
            self.filename_template_input = QLineEdit(self.action_data.get('filename_template', 'data_{timestamp}.txt'))
            form_layout.addRow("Filename Template:", self.filename_template_input)
            
            self.ftp_format_combo = QComboBox()
            self.ftp_format_combo.addItems(['json', 'csv', 'custom', 'structured'])
            self.ftp_format_combo.setCurrentText(self.action_data.get('format', 'json'))
            form_layout.addRow("Format:", self.ftp_format_combo)
        
        layout.addLayout(form_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def on_format_changed(self, format_type: str):
        """Handle format change."""
        if format_type in ['custom', 'structured']:
            self.structure_input.setEnabled(True)
        else:
            self.structure_input.setEnabled(False)
    
    def get_action_data(self) -> Dict[str, Any]:
        """Get action data from form."""
        data = {'type': self.action_type}
        
        if self.action_type == 'api':
            data['url'] = self.url_input.text()
            data['method'] = self.method_combo.currentText()
            try:
                data['headers'] = json.loads(self.headers_input.toPlainText())
            except:
                data['headers'] = {}
            data['timeout'] = self.timeout_input.value()
            data['max_retries'] = self.retries_input.value()
        
        elif self.action_type == 'file':
            data['path'] = self.path_input.text()
            data['format'] = self.format_combo.currentText()
            try:
                data['structure'] = json.loads(self.structure_input.toPlainText())
            except:
                data['structure'] = {}
        
        elif self.action_type == 'ftp':
            data['host'] = self.ftp_host_input.text()
            data['port'] = self.ftp_port_input.value()
            data['user'] = self.ftp_user_input.text()
            data['password'] = self.ftp_password_input.text()
            data['remote_path'] = self.remote_path_input.text()
            data['use_tls'] = self.use_tls_checkbox.isChecked()
            data['filename_template'] = self.filename_template_input.text()
            data['format'] = self.ftp_format_combo.currentText()
        
        return data


class ParsingRuleDialog(QDialog):
    """Dialog for editing parsing rule configuration."""
    
    def __init__(self, rule_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.rule_data = rule_data or {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize dialog UI."""
        self.setWindowTitle("Edit Parsing Rule")
        self.setMinimumSize(600, 500)
        self.resize(700, 550)
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        # Column name
        self.column_input = QLineEdit(self.rule_data.get('column', ''))
        self.column_input.setMinimumWidth(300)
        form_layout.addRow("Column:", self.column_input)
        
        # Rule type
        self.type_combo = QComboBox()
        self.type_combo.addItems(['decimal', 'integer', 'string', 'date', 'custom', 'regex'])
        if self.rule_data.get('type'):
            self.type_combo.setCurrentText(self.rule_data.get('type'))
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        self.type_combo.setMinimumWidth(300)
        form_layout.addRow("Type:", self.type_combo)
        
        # Type-specific options (will be shown/hidden based on type)
        self.options_widget = QWidget()
        self.options_layout = QFormLayout()
        self.options_widget.setLayout(self.options_layout)
        
        # Decimal options
        self.precision_input = QSpinBox()
        self.precision_input.setMinimum(0)
        self.precision_input.setMaximum(10)
        self.precision_input.setValue(self.rule_data.get('precision', 2))
        self.precision_label = QLabel("Precision:")
        self.options_layout.addRow(self.precision_label, self.precision_input)
        
        # String options
        self.format_input = QLineEdit(self.rule_data.get('format', ''))
        self.format_input.setPlaceholderText('e.g., "{value}" or "{:>10}"')
        self.format_input.setMinimumWidth(300)
        self.format_label = QLabel("Format:")
        self.options_layout.addRow(self.format_label, self.format_input)
        
        # Date options
        self.input_format_input = QLineEdit(self.rule_data.get('input_format', '%Y-%m-%d %H:%M:%S'))
        self.input_format_input.setMinimumWidth(300)
        self.input_format_label = QLabel("Input Format:")
        self.options_layout.addRow(self.input_format_label, self.input_format_input)
        
        self.output_format_input = QLineEdit(self.rule_data.get('output_format', '%Y-%m-%d %H:%M:%S'))
        self.output_format_input.setMinimumWidth(300)
        self.output_format_label = QLabel("Output Format:")
        self.options_layout.addRow(self.output_format_label, self.output_format_input)
        
        # Custom options
        self.expression_input = QLineEdit(self.rule_data.get('expression', ''))
        self.expression_input.setPlaceholderText('e.g., "{value} * 2"')
        self.expression_input.setMinimumWidth(300)
        self.expression_label = QLabel("Expression:")
        self.options_layout.addRow(self.expression_label, self.expression_input)
        
        # Regex options
        self.pattern_input = QLineEdit(self.rule_data.get('pattern', ''))
        self.pattern_input.setPlaceholderText('Regex pattern')
        self.pattern_input.setMinimumWidth(300)
        self.pattern_label = QLabel("Pattern:")
        self.options_layout.addRow(self.pattern_label, self.pattern_input)
        
        self.replacement_input = QLineEdit(self.rule_data.get('replacement', ''))
        self.replacement_input.setMinimumWidth(300)
        self.replacement_label = QLabel("Replacement:")
        self.options_layout.addRow(self.replacement_label, self.replacement_input)
        
        form_layout.addRow("Options:", self.options_widget)
        layout.addLayout(form_layout)
        
        # Update visibility based on current type
        self.on_type_changed(self.type_combo.currentText())
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def on_type_changed(self, rule_type: str):
        """Update UI based on selected rule type."""
        # Hide all options
        self.precision_label.setVisible(False)
        self.precision_input.setVisible(False)
        self.format_label.setVisible(False)
        self.format_input.setVisible(False)
        self.input_format_label.setVisible(False)
        self.input_format_input.setVisible(False)
        self.output_format_label.setVisible(False)
        self.output_format_input.setVisible(False)
        self.expression_label.setVisible(False)
        self.expression_input.setVisible(False)
        self.pattern_label.setVisible(False)
        self.pattern_input.setVisible(False)
        self.replacement_label.setVisible(False)
        self.replacement_input.setVisible(False)
        
        # Show relevant options
        if rule_type == 'decimal':
            self.precision_label.setVisible(True)
            self.precision_input.setVisible(True)
        elif rule_type == 'string':
            self.format_label.setVisible(True)
            self.format_input.setVisible(True)
        elif rule_type == 'date':
            self.input_format_label.setVisible(True)
            self.input_format_input.setVisible(True)
            self.output_format_label.setVisible(True)
            self.output_format_input.setVisible(True)
        elif rule_type == 'custom':
            self.expression_label.setVisible(True)
            self.expression_input.setVisible(True)
        elif rule_type == 'regex':
            self.pattern_label.setVisible(True)
            self.pattern_input.setVisible(True)
            self.replacement_label.setVisible(True)
            self.replacement_input.setVisible(True)
    
    def get_rule_data(self) -> Dict[str, Any]:
        """Get rule data from form."""
        data = {
            'column': self.column_input.text(),
            'type': self.type_combo.currentText()
        }
        
        rule_type = data['type']
        if rule_type == 'decimal':
            data['precision'] = self.precision_input.value()
        elif rule_type == 'string':
            if self.format_input.text():
                data['format'] = self.format_input.text()
        elif rule_type == 'date':
            data['input_format'] = self.input_format_input.text()
            data['output_format'] = self.output_format_input.text()
        elif rule_type == 'custom':
            if self.expression_input.text():
                data['expression'] = self.expression_input.text()
        elif rule_type == 'regex':
            data['pattern'] = self.pattern_input.text()
            data['replacement'] = self.replacement_input.text()
        
        return data


class BranchRuleDialog(QDialog):
    """Dialog for editing branch rule configuration."""
    
    def __init__(self, rule_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.rule_data = rule_data or {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize dialog UI."""
        self.setWindowTitle("Edit Branch Rule")
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        # Column name
        self.column_input = QLineEdit(self.rule_data.get('column', ''))
        form_layout.addRow("Column:", self.column_input)
        
        # Match type (exact value or pattern)
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(['Exact Value', 'Pattern (Regex)'])
        if 'pattern' in self.rule_data:
            self.match_type_combo.setCurrentText('Pattern (Regex)')
        self.match_type_combo.currentTextChanged.connect(self.on_match_type_changed)
        form_layout.addRow("Match Type:", self.match_type_combo)
        
        # Value/Pattern input
        self.value_input = QLineEdit(self.rule_data.get('value', ''))
        self.value_input.setPlaceholderText("Exact value to match")
        self.value_label = QLabel("Value:")
        form_layout.addRow(self.value_label, self.value_input)
        
        # Pattern input (initially hidden)
        self.pattern_input = QLineEdit(self.rule_data.get('pattern', ''))
        self.pattern_input.setPlaceholderText("Regex pattern")
        self.pattern_label = QLabel("Pattern:")
        self.pattern_label.setVisible(False)
        self.pattern_input.setVisible(False)
        form_layout.addRow(self.pattern_label, self.pattern_input)
        
        # Folder
        self.folder_input = QLineEdit(self.rule_data.get('folder', ''))
        self.folder_input.setPlaceholderText("folder/x")
        form_layout.addRow("Folder:", self.folder_input)
        
        # Update visibility
        self.on_match_type_changed(self.match_type_combo.currentText())
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def on_match_type_changed(self, match_type: str):
        """Update UI based on match type."""
        if match_type == 'Pattern (Regex)':
            self.value_label.setVisible(False)
            self.value_input.setVisible(False)
            self.pattern_label.setVisible(True)
            self.pattern_input.setVisible(True)
        else:
            self.value_label.setVisible(True)
            self.value_input.setVisible(True)
            self.pattern_label.setVisible(False)
            self.pattern_input.setVisible(False)
    
    def get_rule_data(self) -> Dict[str, Any]:
        """Get rule data from form."""
        data = {
            'column': self.column_input.text(),
            'folder': self.folder_input.text()
        }
        
        if self.match_type_combo.currentText() == 'Pattern (Regex)':
            data['pattern'] = self.pattern_input.text()
        else:
            data['value'] = self.value_input.text()
        
        return data


class ParseTransferTab(QWidget):
    """Tab for parsing rules and action configuration."""
    
    config_saved = Signal()  # Signal emitted when config is saved
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config: Optional[Config] = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout()
        
        # Interval and save row at top
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Check interval (seconds):"))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimum(1)
        self.interval_spinbox.setMaximum(86400)
        self.interval_spinbox.setValue(60)
        self.interval_spinbox.setToolTip("How often to check for new rows")
        top_layout.addWidget(self.interval_spinbox)
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        # Splitter for side-by-side layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()
        
        # Action list
        self.action_list = QListWidget()
        actions_layout.addWidget(self.action_list)
        
        # Action buttons
        action_btn_layout = QHBoxLayout()
        self.add_action_btn = QPushButton("Add Action")
        self.add_action_btn.clicked.connect(self.add_action)
        self.edit_action_btn = QPushButton("Edit Action")
        self.edit_action_btn.clicked.connect(self.edit_action)
        self.delete_action_btn = QPushButton("Delete Action")
        self.delete_action_btn.clicked.connect(self.delete_action)
        
        action_btn_layout.addWidget(self.add_action_btn)
        action_btn_layout.addWidget(self.edit_action_btn)
        action_btn_layout.addWidget(self.delete_action_btn)
        actions_layout.addLayout(action_btn_layout)
        
        actions_group.setLayout(actions_layout)
        splitter.addWidget(actions_group)
        
        # Right side: Parsing Rules and Branch Rules
        rules_widget = QWidget()
        rules_layout = QVBoxLayout()
        
        # Parsing Rules
        parsing_group = QGroupBox("Parsing Rules")
        parsing_layout = QVBoxLayout()
        
        self.parsing_list = QListWidget()
        parsing_layout.addWidget(self.parsing_list)
        
        parsing_btn_layout = QHBoxLayout()
        self.add_parsing_btn = QPushButton("Add Rule")
        self.add_parsing_btn.clicked.connect(self.add_parsing_rule)
        self.edit_parsing_btn = QPushButton("Edit Rule")
        self.edit_parsing_btn.clicked.connect(self.edit_parsing_rule)
        self.delete_parsing_btn = QPushButton("Delete Rule")
        self.delete_parsing_btn.clicked.connect(self.delete_parsing_rule)
        
        parsing_btn_layout.addWidget(self.add_parsing_btn)
        parsing_btn_layout.addWidget(self.edit_parsing_btn)
        parsing_btn_layout.addWidget(self.delete_parsing_btn)
        parsing_layout.addLayout(parsing_btn_layout)
        
        parsing_group.setLayout(parsing_layout)
        rules_layout.addWidget(parsing_group)
        
        # Branch Rules
        branch_group = QGroupBox("Branch Rules")
        branch_layout = QVBoxLayout()
        
        self.branch_list = QListWidget()
        branch_layout.addWidget(self.branch_list)
        
        branch_btn_layout = QHBoxLayout()
        self.add_branch_btn = QPushButton("Add Rule")
        self.add_branch_btn.clicked.connect(self.add_branch_rule)
        self.edit_branch_btn = QPushButton("Edit Rule")
        self.edit_branch_btn.clicked.connect(self.edit_branch_rule)
        self.delete_branch_btn = QPushButton("Delete Rule")
        self.delete_branch_btn.clicked.connect(self.delete_branch_rule)
        
        branch_btn_layout.addWidget(self.add_branch_btn)
        branch_btn_layout.addWidget(self.edit_branch_btn)
        branch_btn_layout.addWidget(self.delete_branch_btn)
        branch_layout.addLayout(branch_btn_layout)
        
        branch_group.setLayout(branch_layout)
        rules_layout.addWidget(branch_group)
        
        rules_widget.setLayout(rules_layout)
        splitter.addWidget(rules_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.clicked.connect(self.save_config)
        save_layout.addWidget(self.save_btn)
        layout.addLayout(save_layout)
        
        self.setLayout(layout)
    
    def set_config(self, config: Config):
        """Load configuration into UI."""
        self.config = config
        if config:
            self.interval_spinbox.setValue(int(config.interval_seconds))
        self.refresh_lists()
    
    def refresh_lists(self):
        """Refresh action and rule lists."""
        if not self.config:
            return
        
        # Refresh actions
        self.action_list.clear()
        for i, action in enumerate(self.config.actions):
            action_type = action.get('type', 'unknown')
            if action_type == 'api':
                label = f"API: {action.get('url', 'N/A')}"
            elif action_type == 'file':
                label = f"File: {action.get('path', 'N/A')}"
            elif action_type == 'ftp':
                label = f"FTP: {action.get('host', 'N/A')}"
            else:
                label = f"{action_type}: {i}"
            self.action_list.addItem(label)
        
        # Refresh parsing rules
        self.parsing_list.clear()
        for rule in self.config.parsing_rules:
            column = rule.get('column', 'N/A')
            rule_type = rule.get('type', 'N/A')
            # Add type-specific details
            details = []
            if rule_type == 'decimal' and 'precision' in rule:
                details.append(f"precision={rule['precision']}")
            elif rule_type == 'string' and 'format' in rule:
                details.append(f"format={rule['format'][:20]}")
            elif rule_type == 'date':
                if 'input_format' in rule:
                    details.append(f"in={rule['input_format']}")
                if 'output_format' in rule:
                    details.append(f"out={rule['output_format']}")
            elif rule_type == 'custom' and 'expression' in rule:
                details.append(f"expr={rule['expression'][:20]}")
            elif rule_type == 'regex' and 'pattern' in rule:
                details.append(f"pattern={rule['pattern'][:20]}")
            
            detail_str = f" - {', '.join(details)}" if details else ""
            label = f"{column} ({rule_type}{detail_str})"
            self.parsing_list.addItem(label)
        
        # Refresh branch rules
        self.branch_list.clear()
        for rule in self.config.branch_rules:
            column = rule.get('column', 'N/A')
            folder = rule.get('folder', 'N/A')
            if 'pattern' in rule:
                pattern = rule.get('pattern', 'N/A')
                label = f"{column} ~ {pattern} -> {folder}"
            else:
                value = rule.get('value', 'N/A')
                label = f"{column} = {value} -> {folder}"
            self.branch_list.addItem(label)
    
    def add_action(self):
        """Add a new action."""
        if not self.config:
            return
        
        # Show dialog to select action type
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Action Type")
        layout = QVBoxLayout()
        
        type_combo = QComboBox()
        type_combo.addItems(['api', 'file', 'ftp'])
        layout.addWidget(QLabel("Action Type:"))
        layout.addWidget(type_combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            action_type = type_combo.currentText()
            action_dialog = ActionDialog(action_type, parent=self)
            if action_dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    action_data = action_dialog.get_action_data()
                    self.config.add_action(action_data)
                    self.refresh_lists()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to add action: {e}")
    
    def edit_action(self):
        """Edit selected action."""
        if not self.config:
            return
        
        current_item = self.action_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select an action to edit")
            return
        
        index = self.action_list.currentRow()
        action_data = self.config.actions[index]
        action_type = action_data.get('type')
        
        action_dialog = ActionDialog(action_type, action_data, parent=self)
        if action_dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                new_action_data = action_dialog.get_action_data()
                self.config.update_action(index, new_action_data)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update action: {e}")
    
    def delete_action(self):
        """Delete selected action."""
        if not self.config:
            return
        
        current_item = self.action_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select an action to delete")
            return
        
        index = self.action_list.currentRow()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete this action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.config.remove_action(index)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete action: {e}")
    
    def add_parsing_rule(self):
        """Add a new parsing rule."""
        if not self.config:
            return
        
        dialog = ParsingRuleDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                rule_data = dialog.get_rule_data()
                if not rule_data.get('column'):
                    QMessageBox.warning(self, "Warning", "Column name is required")
                    return
                self.config.add_parsing_rule(rule_data)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add parsing rule: {e}")
    
    def edit_parsing_rule(self):
        """Edit selected parsing rule."""
        if not self.config:
            return
        
        current_item = self.parsing_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a parsing rule to edit")
            return
        
        index = self.parsing_list.currentRow()
        rule_data = self.config.parsing_rules[index]
        
        dialog = ParsingRuleDialog(rule_data, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                new_rule_data = dialog.get_rule_data()
                if not new_rule_data.get('column'):
                    QMessageBox.warning(self, "Warning", "Column name is required")
                    return
                self.config.update_parsing_rule(index, new_rule_data)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update parsing rule: {e}")
    
    def delete_parsing_rule(self):
        """Delete selected parsing rule."""
        if not self.config:
            return
        
        current_item = self.parsing_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a rule to delete")
            return
        
        index = self.parsing_list.currentRow()
        try:
            self.config.remove_parsing_rule(index)
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete rule: {e}")
    
    def add_branch_rule(self):
        """Add a new branch rule."""
        if not self.config:
            return
        
        dialog = BranchRuleDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                rule_data = dialog.get_rule_data()
                if not rule_data.get('column') or not rule_data.get('folder'):
                    QMessageBox.warning(self, "Warning", "Column name and folder are required")
                    return
                if 'value' not in rule_data and 'pattern' not in rule_data:
                    QMessageBox.warning(self, "Warning", "Either value or pattern is required")
                    return
                self.config.add_branch_rule(rule_data)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add branch rule: {e}")
    
    def edit_branch_rule(self):
        """Edit selected branch rule."""
        if not self.config:
            return
        
        current_item = self.branch_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a branch rule to edit")
            return
        
        index = self.branch_list.currentRow()
        rule_data = self.config.branch_rules[index]
        
        dialog = BranchRuleDialog(rule_data, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                new_rule_data = dialog.get_rule_data()
                if not new_rule_data.get('column') or not new_rule_data.get('folder'):
                    QMessageBox.warning(self, "Warning", "Column name and folder are required")
                    return
                if 'value' not in new_rule_data and 'pattern' not in new_rule_data:
                    QMessageBox.warning(self, "Warning", "Either value or pattern is required")
                    return
                self.config.update_branch_rule(index, new_rule_data)
                self.refresh_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update branch rule: {e}")
    
    def delete_branch_rule(self):
        """Delete selected branch rule."""
        if not self.config:
            return
        
        current_item = self.branch_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a rule to delete")
            return
        
        index = self.branch_list.currentRow()
        try:
            self.config.remove_branch_rule(index)
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete rule: {e}")
    
    def save_config(self):
        """Save configuration."""
        if not self.config:
            QMessageBox.warning(self, "Error", "No configuration loaded")
            return
        
        try:
            self.config.update_interval(float(self.interval_spinbox.value()))
            self.config.save()
            QMessageBox.information(self, "Success", "Configuration saved successfully!")
            # Emit signal to notify main window
            self.config_saved.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.config_path = config_path
        self.config: Optional[Config] = None
        self.app: Optional[DataParserApp] = None
        self.log_handler = GUILogHandler()
        self.init_ui()
        self.load_config()
    
    def init_ui(self):
        """Initialize UI."""
        self.setWindowTitle("MySQL Data Parser and Transmitter")
        self.setMinimumSize(1000, 700)
        
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Create tabs
        self.tabs = QTabWidget()
        
        # Program Run tab
        self.program_tab = ProgramRunTab()
        self.program_tab.add_log_handler(self.log_handler)
        self.tabs.addTab(self.program_tab, "Program Run")
        
        # DB Config tab
        self.db_tab = DBConfigTab()
        self.db_tab.config_saved.connect(self.reload_config)
        self.tabs.addTab(self.db_tab, "DB Config")
        
        # Parse/Transfer tab
        self.parse_tab = ParseTransferTab()
        self.parse_tab.config_saved.connect(self.reload_config)
        self.tabs.addTab(self.parse_tab, "Parse/Transfer")
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs)
        
        # Apply stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a90e2;
                color: white;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2a5f8f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
    
    def load_config(self):
        """Load configuration."""
        try:
            self.config = Config(self.config_path)
            # Only create new app if not running, otherwise update config
            if not self.app or not self.app.running:
                self.app = DataParserApp(self.config_path)
                self.program_tab.set_app(self.app)
            else:
                # If running, just update the config reference
                self.app.config = self.config
            
            # Update tabs with config
            self.db_tab.set_config(self.config)
            self.parse_tab.set_config(self.config)
            self.program_tab.set_config(self.config)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration: {e}")
    
    def reload_config(self):
        """Reload configuration from file."""
        self.load_config()
    
    def on_tab_changed(self, index: int):
        """Sync interval display when switching to Parse/Transfer tab."""
        if self.config and index == 2:
            self.parse_tab.interval_spinbox.setValue(int(self.config.interval_seconds))
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.program_tab.monitoring_thread:
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Monitoring is running. Do you want to stop and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.program_tab.stop_monitoring()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
