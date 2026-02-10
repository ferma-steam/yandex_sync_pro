"""
Управление метаданными и историей операций через SQLite
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

class MetadataManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()
        logging.info(f"MetadataManager инициализирован: {db_path}")
    
    def _init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Таблица метаданных файлов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_metadata (
                    filepath TEXT PRIMARY KEY,
                    cloud_path TEXT NOT NULL,
                    cloud_hash TEXT,
                    local_hash TEXT,
                    last_sync TEXT,
                    status TEXT DEFAULT 'pending',
                    size INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица истории операций
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    operation TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    size INTEGER DEFAULT 0,
                    details TEXT,
                    duration REAL DEFAULT 0
                )
            """)
            
            # Таблица статистики по папкам
            conn.execute("""
                CREATE TABLE IF NOT EXISTS folder_statistics (
                    folder_path TEXT PRIMARY KEY,
                    file_count INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица настроек приложения
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Индексы для ускорения запросов
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON operation_history(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_operation ON operation_history(operation)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON operation_history(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metadata_status ON file_metadata(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metadata_last_sync ON file_metadata(last_sync)")
            
            conn.commit()
    
    def update_file_metadata(self, filepath: str, cloud_hash: str, cloud_path: str, 
                           last_sync: str, status: str, size: int = 0):
        """Обновление метаданных файла"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO file_metadata 
                (filepath, cloud_path, cloud_hash, last_sync, status, size)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(filepath) DO UPDATE SET
                    cloud_path = excluded.cloud_path,
                    cloud_hash = excluded.cloud_hash,
                    last_sync = excluded.last_sync,
                    status = excluded.status,
                    size = excluded.size
            """, (filepath, cloud_path, cloud_hash, last_sync, status, size))
            conn.commit()
    
    def get_file_metadata(self, filepath: str) -> Optional[Dict]:
        """Получение метаданных файла"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT filepath, cloud_path, cloud_hash, last_sync, status, size
                FROM file_metadata WHERE filepath = ?
            """, (filepath,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'filepath': row[0],
                    'cloud_path': row[1],
                    'cloud_hash': row[2],
                    'last_sync': row[3],
                    'status': row[4],
                    'size': row[5]
                }
            return None
    
    def add_operation(self, operation: str, path: str, status: str, 
                     size: int = 0, details: str = '', duration: float = 0.0):
        """Добавление записи в историю операций"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO operation_history 
                (operation, path, status, size, details, duration)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (operation, path, status, size, details, duration))
            conn.commit()
    
    def get_operation_history(self, filters: Optional[Dict] = None) -> List[Dict]:
        """Получение истории операций с фильтрацией"""
        query = """
            SELECT id, timestamp, operation, path, status, size, details, duration
            FROM operation_history
            WHERE 1=1
        """
        params = []
        
        # Фильтрация по операции
        if filters and filters.get('operation'):
            query += " AND operation = ?"
            params.append(filters['operation'])
        
        # Фильтрация по периоду
        if filters and filters.get('period'):
            period = filters['period']
            if period == 'today':
                query += " AND timestamp >= datetime('now', 'start of day')"
            elif period == 'week':
                query += " AND timestamp >= datetime('now', '-7 days')"
            elif period == 'month':
                query += " AND timestamp >= datetime('now', '-30 days')"
        
        # Поиск по пути
        if filters and filters.get('search'):
            query += " AND path LIKE ?"
            params.append(f"%{filters['search']}%")
        
        query += " ORDER BY timestamp DESC LIMIT 1000"
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'timestamp': row[1],
                'operation': row[2],
                'path': row[3],
                'status': row[4],
                'size': row[5],
                'details': row[6],
                'duration': row[7]
            } for row in rows]
    
    def clear_operation_history(self, before_date: Optional[str] = None):
        """Очистка истории операций"""
        with sqlite3.connect(self.db_path) as conn:
            if before_date:
                conn.execute("DELETE FROM operation_history WHERE timestamp < ?", (before_date,))
            else:
                conn.execute("DELETE FROM operation_history")
            conn.commit()
    
    def update_folder_statistics(self, folder_path: str, file_count: int, total_size: int):
        """Обновление статистики папки"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO folder_statistics (folder_path, file_count, total_size, last_updated)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(folder_path) DO UPDATE SET
                    file_count = excluded.file_count,
                    total_size = excluded.total_size,
                    last_updated = datetime('now')
            """, (folder_path, file_count, total_size))
            conn.commit()
    
    def get_sync_statistics(self) -> Dict:
        """Получение общей статистики синхронизации"""
        with sqlite3.connect(self.db_path) as conn:
            # Всего файлов
            cursor = conn.execute("SELECT COUNT(*) FROM file_metadata WHERE status = 'synced'")
            total_files = cursor.fetchone()[0]
            
            # Файлы за сегодня
            cursor = conn.execute("""
                SELECT COUNT(*) FROM operation_history 
                WHERE operation IN ('upload', 'download') 
                AND status = 'success'
                AND timestamp >= datetime('now', 'start of day')
            """)
            today_files = cursor.fetchone()[0]
            
            # Общий трафик
            cursor = conn.execute("""
                SELECT SUM(size) FROM operation_history 
                WHERE operation IN ('upload', 'download') AND status = 'success'
            """)
            total_bytes = cursor.fetchone()[0] or 0
            
            # Последняя синхронизация
            cursor = conn.execute("""
                SELECT MAX(last_sync) FROM file_metadata WHERE status = 'synced'
            """)
            last_sync = cursor.fetchone()[0]
            
            return {
                'total_files': total_files,
                'today_files': today_files,
                'total_bytes': total_bytes,
                'last_sync': last_sync
            }
    
    def get_traffic_history(self, days: int = 7) -> List[Dict]:
        """Получение истории трафика за период"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    DATE(timestamp) as date,
                    SUM(CASE WHEN operation = 'upload' THEN size ELSE 0 END) as upload,
                    SUM(CASE WHEN operation = 'download' THEN size ELSE 0 END) as download
                FROM operation_history
                WHERE timestamp >= datetime('now', ?)
                AND operation IN ('upload', 'download')
                AND status = 'success'
                GROUP BY DATE(timestamp)
                ORDER BY date
            """, (f'-{days} days',))
            
            rows = cursor.fetchall()
            return [{
                'date': row[0],
                'upload': row[1] or 0,
                'download': row[2] or 0
            } for row in rows]
    
    def get_files_history(self, days: int = 30) -> List[Dict]:
        """Получение истории количества файлов за период"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as count
                FROM operation_history
                WHERE timestamp >= datetime('now', ?)
                AND operation IN ('upload', 'download')
                AND status = 'success'
                GROUP BY DATE(timestamp)
                ORDER BY date
            """, (f'-{days} days',))
            
            rows = cursor.fetchall()
            return [{
                'date': row[0],
                'count': row[1]
            } for row in rows]
    
    def set_setting(self, key: str, value):
        """Сохранение настройки приложения"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, json.dumps(value) if not isinstance(value, str) else value))
            conn.commit()
    
    def get_setting(self, key: str, default=None):
        """Получение настройки приложения"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except:
                    return row[0]
            return default
    
    def close(self):
        """Закрытие соединения (для совместимости)"""
        pass  # SQLite управляет соединениями автоматически
    
    def vacuum(self):
        """Оптимизация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("VACUUM")
            conn.commit()
        logging.info("База данных оптимизирована (VACUUM)")