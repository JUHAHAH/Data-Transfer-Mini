"""
Main application entry point for MySQL Data Parser and Transmitter.
"""
import sys
import time
import signal
import logging
from typing import Optional
import schedule

def _pause_on_error():
    """Pause console on Windows to allow viewing error messages."""
    if sys.platform == 'win32':
        try:
            input("\nPress Enter to exit...")
        except:
            import time
            time.sleep(5)  # Fallback: wait 5 seconds

try:
    from config import Config, ConfigError
    from database import Database, DatabaseError
    from state import StateManager
    from parser import DataParser
    from actions import ActionExecutor, FTPLoginFailedException
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    print("Make sure all Python files (actions.py, config.py, database.py, parser.py, state.py) are in the same directory.")
    _pause_on_error()
    sys.exit(1)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_parser.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DataParserApp:
    """Main application class."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the application.
        
        Args:
            config_path: Path to configuration file
        """
        self.running = False
        self.config: Optional[Config] = None
        self.database: Optional[Database] = None
        self.state_manager: Optional[StateManager] = None
        self.parser: Optional[DataParser] = None
        self.action_executor: Optional[ActionExecutor] = None
        self.config_path = config_path
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False
    
    def initialize(self):
        """Initialize all components."""
        # Load configuration
        logger.info("Loading configuration...")
        self.config = Config(self.config_path)
        
        # Initialize database
        logger.info("Connecting to database...")
        self.database = Database(self.config.database)
        if not self.database.test_connection():
            raise DatabaseError("Database connection test failed")
        
        # Initialize state manager
        logger.info("Initializing state manager...")
        table_name = self.config.database['table']
        self.state_manager = StateManager()
        
        # Initialize parser
        logger.info("Initializing parser...")
        self.parser = DataParser(
            parsing_rules=self.config.parsing_rules,
            branch_rules=self.config.branch_rules,
            output_format=self.config.output_format
        )
        
        # Initialize action executor
        logger.info("Initializing action executor...")
        self.action_executor = ActionExecutor(
            self.config.actions,
            ftp_global_defaults=self.config.ftp_global_defaults,
        )
        
        logger.info("Initialization complete!")
    
    def process_new_rows(self):
        """Process new rows from database. On any error, stops monitoring and re-raises."""
        try:
            table_name = self.config.database['table']
            id_column = self.config.database['id_column']
            
            # Get last processed ID
            last_id = self.state_manager.get_last_processed_id(table_name)
            logger.info(f"Last processed ID: {last_id}")
            
            # Query for new rows
            rows = self.database.get_new_rows(table_name, id_column, last_id)
            
            if not rows:
                logger.debug("No new rows found")
                return
            
            logger.info(f"Found {len(rows)} new row(s)")
            
            # Buffer FTP by file so we upload once per file (one connection, one APPE) instead of per row
            self.action_executor.start_ftp_batch()
            
            # Process each row
            max_id = last_id if last_id else 0
            for row in rows:
                try:
                    # Parse row
                    parsed_row = self.parser.parse_row(row)
                    
                    # Execute actions (FTP buffered; file/api run immediately)
                    results = self.action_executor.execute_actions(parsed_row, self.parser)
                    
                    # Track success
                    success_count = sum(1 for r in results if r)
                    logger.info(f"Processed row ID {row[id_column]}: {success_count}/{len(results)} actions succeeded")
                    
                    # Update max ID
                    current_id = row.get(id_column)
                    if current_id and (max_id is None or current_id > max_id):
                        max_id = current_id
                
                except FTPLoginFailedException as e:
                    logger.error(f"FTP login failed repeatedly: {e}")
                    logger.error("Stopping monitoring due to FTP login failures.")
                    self.stop_monitoring()
                    raise
                except Exception as e:
                    logger.error(f"Error processing row {row.get(id_column)}: {e}", exc_info=True)
                    logger.error("Stopping monitoring due to error.")
                    self.stop_monitoring()
                    raise
            
            # Upload all buffered FTP data (one connection per file)
            try:
                self.action_executor.flush_ftp_buffers()
            except Exception as e:
                logger.error(f"FTP batch upload failed: {e}", exc_info=True)
                logger.error("Stopping monitoring due to error.")
                self.stop_monitoring()
                raise
            
            # Update state with last processed ID
            if max_id > (last_id or 0):
                self.state_manager.set_last_processed_id(max_id, table_name)
                logger.info(f"Updated last processed ID to: {max_id}")
        
        except FTPLoginFailedException:
            raise  # Already logged and stop_monitoring() called in per-row handler
        except DatabaseError as e:
            logger.error(f"Database error during processing: {e}")
            logger.error("Stopping monitoring due to error.")
            self.stop_monitoring()
            raise
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}", exc_info=True)
            logger.error("Stopping monitoring due to error.")
            self.stop_monitoring()
            raise
    
    def run(self):
        """Run the main application loop."""
        self.initialize()
        self.start_monitoring()
        
        # Main loop
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)  # Check every second for scheduled tasks
        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            logger.info("Shutting down...")
            self.shutdown()
    
    def run_monitoring_loop(self):
        """Run the monitoring loop (for use in threads)."""
        while self.running:
            schedule.run_pending()
            time.sleep(1)  # Check every second for scheduled tasks
    
    def shutdown(self):
        """Cleanup and shutdown."""
        if self.database:
            # Database connections are managed by pool and will close automatically
            pass
        logger.info("Shutdown complete")
    
    def start_monitoring(self):
        """Start monitoring in a thread-safe way."""
        if self.running:
            logger.warning("Monitoring is already running")
            return
        
        if not self.config or not self.database:
            raise RuntimeError("Application not initialized. Call initialize() first.")
        
        interval_seconds = self.config.interval_seconds
        
        logger.info(f"Starting data parser (check interval: {interval_seconds} seconds)")
        logger.info(f"Monitoring table: {self.config.database['table']}")
        
        # Clear existing schedule
        schedule.clear()
        
        # Schedule the processing job
        schedule.every(interval_seconds).seconds.do(self.process_new_rows)
        
        # Process immediately on startup
        self.process_new_rows()
        
        self.running = True
    
    def stop_monitoring(self):
        """Stop monitoring gracefully."""
        if not self.running:
            logger.warning("Monitoring is not running")
            return
        
        logger.info("Stopping monitoring...")
        self.running = False
        schedule.clear()
        logger.info("Monitoring stopped")
    
    def get_status(self) -> dict:
        """Get current status information."""
        status = {
            'running': self.running,
            'initialized': self.config is not None and self.database is not None,
        }
        
        if self.config:
            status['interval'] = self.config.interval_seconds
            status['table'] = self.config.database.get('table', 'N/A')
        
        if self.state_manager and self.config:
            table_name = self.config.database.get('table')
            status['last_processed_id'] = self.state_manager.get_last_processed_id(table_name)
        else:
            status['last_processed_id'] = None
        
        return status
    
    def set_interval(self, interval_seconds: float):
        """Update check interval dynamically."""
        if not isinstance(interval_seconds, (int, float)) or interval_seconds <= 0:
            raise ValueError("interval_seconds must be a positive number")
        
        if self.config:
            self.config.update_interval(interval_seconds)
        
        # If monitoring is running, reschedule
        if self.running:
            schedule.clear()
            schedule.every(interval_seconds).seconds.do(self.process_new_rows)
            logger.info(f"Interval updated to {interval_seconds} seconds")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='MySQL Data Parser and Transmitter')
    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Path to configuration file (default: config.json)'
    )
    parser.add_argument(
        '--gui',
        action='store_true',
        help='Launch GUI interface'
    )
    
    args = parser.parse_args()
    
    # Check if GUI mode requested
    if args.gui or (len(sys.argv) == 1 and sys.platform != 'linux'):
        # Launch GUI
        try:
            from gui_main import main as gui_main
            gui_main(config_path=args.config)
        except ImportError as e:
            logger.error(f"GUI module not found. Install PySide6: pip install PySide6")
            logger.error(f"Import error details: {e}")
            _pause_on_error()
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to launch GUI: {e}", exc_info=True)
            _pause_on_error()
            sys.exit(1)
    else:
        # CLI mode
        app = DataParserApp(config_path=args.config)
        try:
            app.initialize()
            app.run()
        except ConfigError as e:
            logger.error(f"Configuration error: {e}")
            _pause_on_error()
            sys.exit(1)
        except DatabaseError as e:
            logger.error(f"Database error: {e}")
            _pause_on_error()
            sys.exit(1)
        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            _pause_on_error()
            sys.exit(1)


def _pause_on_error():
    """Pause console on Windows to allow viewing error messages."""
    if sys.platform == 'win32':
        try:
            input("\nPress Enter to exit...")
        except:
            import time
            time.sleep(5)  # Fallback: wait 5 seconds


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        _pause_on_error()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        _pause_on_error()
        sys.exit(1)
