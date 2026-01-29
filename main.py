"""
Main application entry point for MySQL Data Parser and Transmitter.
"""
import sys
import time
import signal
import logging
from typing import Optional
import schedule

from config import Config, ConfigError
from database import Database, DatabaseError
from state import StateManager
from parser import DataParser
from actions import ActionExecutor


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
        try:
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
            self.action_executor = ActionExecutor(self.config.actions)
            
            logger.info("Initialization complete!")
            
        except ConfigError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except DatabaseError as e:
            logger.error(f"Database error: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Initialization error: {e}", exc_info=True)
            sys.exit(1)
    
    def process_new_rows(self):
        """Process new rows from database."""
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
            
            # Process each row
            max_id = last_id if last_id else 0
            for row in rows:
                try:
                    # Parse row
                    parsed_row = self.parser.parse_row(row)
                    
                    # Execute actions
                    results = self.action_executor.execute_actions(parsed_row, self.parser)
                    
                    # Track success
                    success_count = sum(1 for r in results if r)
                    logger.info(f"Processed row ID {row[id_column]}: {success_count}/{len(results)} actions succeeded")
                    
                    # Update max ID
                    current_id = row.get(id_column)
                    if current_id and (max_id is None or current_id > max_id):
                        max_id = current_id
                
                except Exception as e:
                    logger.error(f"Error processing row {row.get(id_column)}: {e}", exc_info=True)
                    # Continue processing other rows
            
            # Update state with last processed ID
            if max_id > (last_id or 0):
                self.state_manager.set_last_processed_id(max_id, table_name)
                logger.info(f"Updated last processed ID to: {max_id}")
        
        except DatabaseError as e:
            logger.error(f"Database error during processing: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}", exc_info=True)
    
    def run(self):
        """Run the main application loop."""
        self.initialize()
        
        if not self.config or not self.database:
            logger.error("Failed to initialize application")
            return
        
        interval_seconds = self.config.interval_seconds
        
        logger.info(f"Starting data parser (check interval: {interval_seconds} seconds)")
        logger.info(f"Monitoring table: {self.config.database['table']}")
        
        # Schedule the processing job
        schedule.every(interval_seconds).seconds.do(self.process_new_rows)
        
        # Process immediately on startup
        self.process_new_rows()
        
        self.running = True
        
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
    
    def shutdown(self):
        """Cleanup and shutdown."""
        if self.database:
            # Database connections are managed by pool and will close automatically
            pass
        logger.info("Shutdown complete")


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
    
    args = parser.parse_args()
    
    app = DataParserApp(config_path=args.config)
    app.run()


if __name__ == '__main__':
    main()
