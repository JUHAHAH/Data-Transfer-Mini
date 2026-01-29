"""
Database module for MySQL connection and query handling.
"""
import mysql.connector
from mysql.connector import Error, pooling
from typing import List, Dict, Any, Optional
import time


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


class Database:
    """MySQL database connection and query handler."""
    
    def __init__(self, config: Dict[str, Any], max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize database connection.
        
        Args:
            config: Database configuration dictionary
            max_retries: Maximum number of connection retries
            retry_delay: Delay between retries in seconds
        """
        self.config = config
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.pool: Optional[pooling.MySQLConnectionPool] = None
        self._connect()
    
    def _connect(self):
        """Establish database connection pool."""
        pool_config = {
            'pool_name': 'mysql_pool',
            'pool_size': 5,
            'pool_reset_session': True,
            'host': self.config['host'],
            'port': self.config['port'],
            'user': self.config['user'],
            'password': self.config['password'],
            'database': self.config['database'],
            'autocommit': True,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci'
        }
        
        for attempt in range(self.max_retries):
            try:
                self.pool = pooling.MySQLConnectionPool(**pool_config)
                # Test connection
                conn = self.pool.get_connection()
                conn.close()
                print(f"Successfully connected to MySQL database: {self.config['database']}")
                return
            except Error as e:
                if attempt < self.max_retries - 1:
                    print(f"Connection attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(self.retry_delay)
                else:
                    raise DatabaseError(f"Failed to connect to database after {self.max_retries} attempts: {e}")
    
    def get_connection(self):
        """
        Get a connection from the pool.
        
        Returns:
            MySQL connection object
        """
        if not self.pool:
            self._connect()
        
        try:
            return self.pool.get_connection()
        except Error as e:
            # Try to reconnect
            self._connect()
            return self.pool.get_connection()
    
    def get_new_rows(self, table_name: str, id_column: str, last_processed_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Query for new rows since last processed ID.
        
        Args:
            table_name: Name of the table to query
            id_column: Name of the ID column
            last_processed_id: Last processed ID (None to get all rows)
        
        Returns:
            List of dictionaries representing rows
        """
        conn = None
        cursor = None
        
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            if last_processed_id is not None:
                query = f"SELECT * FROM `{table_name}` WHERE `{id_column}` > %s ORDER BY `{id_column}` ASC"
                cursor.execute(query, (last_processed_id,))
            else:
                query = f"SELECT * FROM `{table_name}` ORDER BY `{id_column}` ASC LIMIT 1000"
                cursor.execute(query)
            
            rows = cursor.fetchall()
            return rows
        
        except Error as e:
            raise DatabaseError(f"Error querying database: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def test_connection(self) -> bool:
        """
        Test database connection.
        
        Returns:
            True if connection is successful
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Error as e:
            print(f"Connection test failed: {e}")
            return False
