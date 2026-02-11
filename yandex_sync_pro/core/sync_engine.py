"""
Движок синхронизации с поддержкой двусторонней синхронизации и разрешения конфликтов
"""
import os
import time
import threading
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import yadisk
import requests

from .cloud_api import YandexDiskAPI

class SyncStatus:
    SYNCED = "synced"
    SYNCING = "syncing"
    ERROR = "error"
    CONFLICT = "conflict"
    PENDING = "pending"

class SyncEngine:
    def __init__(self, metadata_manager):
        self.metadata = metadata_manager
        self.yadisk_api = YandexDiskAPI()
        self.sync_folders: List[Dict] = []
        self.sync_status: Dict[str, str] = {}
        self.sync_thread: Optional[threading.Thread] = None
        self.observer_threads: List[threading.Thread] = []
        self.running = False
        self._lock = threading.Lock()
        self._last_cloud_check = {}
        self.DELETE_MARKER = ".yd_delete"
        self.CONFLICT_MARKER = "_conflict_"
        self.TRASH_FOLDER = ".yd_trash"
        
        logging.info("SyncEngine инициализирован")
    
    def start_sync(self, folders: List[Dict]):
        """Запуск синхронизации для списка папок"""
        with self._lock:
            if self.running:
                return
            
            self.sync_folders = folders
            self.running = True
            self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True, name="SyncLoop")
            self.sync_thread.start()
            
            # Запуск наблюдателей за файловой системой
            for folder in self.sync_folders:
                thread = threading.Thread(
                    target=self._watch_folder, 
                    args=(folder,), 
                    daemon=True,
                    name=f"Watcher-{folder['local'][:20]}"
                )
                thread.start()
                self.observer_threads.append(thread)
            
            logging.info(f"Синхронизация запущена для {len(folders)} папок")
    
    def stop_sync(self):
        """Остановка синхронизации"""
        with self._lock:
            self.running = False
        
        if self.sync_thread:
            self.sync_thread.join(timeout=5.0)
        
        for thread in self.observer_threads:
            thread.join(timeout=2.0)
        
        self.observer_threads.clear()
        logging.info("Синхронизация остановлена")
    
    def is_running(self) -> bool:
        return self.running
    
    def _sync_loop(self):
        """Основной цикл синхронизации"""
        while self.running:
            for folder in self.sync_folders:
                if not self.running:
                    break
                
                try:
                    # 1. Полная локальная проверка
                    self._full_local_scan(folder)
                    
                    # 2. Для двусторонней синхронизации - проверка облака
                    if folder.get('mode') == 'two_way':
                        self._check_cloud_changes(folder)
                    
                    # 3. Обновление статистики
                    self._update_statistics(folder)
                    
                except Exception as e:
                    logging.error(f"Ошибка в цикле синхронизации для {folder['local']}: {e}")
            
            # Интервал между полными проверками
            for i in range(30):
                if not self.running:
                    break
                time.sleep(1)
    
    def _watch_folder(self, folder: Dict):
        """Наблюдение за изменениями в папке в реальном времени"""
        local_path = Path(folder['local'])
        last_event_time = {}
        
        while self.running:
            try:
                # Сканируем изменения каждые 2 секунды
                current_files = {}
                for root, _, files in os.walk(local_path):
                    for file in files:
                        if self._is_ignored_file(file):
                            continue
                        
                        filepath = Path(root) / file
                        try:
                            stat = filepath.stat()
                            mtime = stat.st_mtime
                            size = stat.st_size
                            
                            current_files[str(filepath)] = (mtime, size)
                            
                            # Проверка на изменения
                            key = str(filepath)
                            if key in last_event_time:
                                last_mtime, last_size = last_event_time[key]
                                if mtime > last_mtime or size != last_size:
                                    # Файл изменён или создан
                                    self._handle_file_event(filepath, folder, 'modified')
                            else:
                                # Новый файл
                                self._handle_file_event(filepath, folder, 'created')
                            
                            last_event_time[key] = (mtime, size)
                        
                        except Exception as e:
                            logging.debug(f"Ошибка сканирования файла {filepath}: {e}")
                
                # Проверка удалённых файлов
                for filepath_str in list(last_event_time.keys()):
                    if filepath_str not in current_files:
                        filepath = Path(filepath_str)
                        if not self._is_ignored_file(filepath.name):
                            self._handle_file_event(filepath, folder, 'deleted')
                        del last_event_time[filepath_str]
                
                time.sleep(2)
                
            except Exception as e:
                logging.error(f"Ошибка наблюдателя за папкой {folder['local']}: {e}")
                time.sleep(5)  # Пауза при ошибке
    
    def _handle_file_event(self, filepath: Path, folder: Dict, event_type: str):
        """Обработка события файловой системы"""
        if not self.running:
            return
        
        rel_path = filepath.relative_to(folder['local'])
        
        # Игнорируем служебные файлы
        if self._is_ignored_file(filepath.name):
            return
        
        # Обработка маркера удаления
        if filepath.name.endswith(self.DELETE_MARKER):
            if event_type == 'created' or event_type == 'modified':
                self._handle_delete_marker(filepath, folder)
            return
        
        # Обработка обычных файлов
        if event_type == 'modified' or event_type == 'created':
            self._sync_file(str(filepath), folder)
        elif event_type == 'deleted':
            self._handle_file_deletion(filepath, folder)
    
    def _handle_delete_marker(self, marker_path: Path, folder: Dict):
        """Обработка маркера удаления (.yd_delete)"""
        # Извлекаем путь к оригинальному файлу
        original_path = Path(str(marker_path).replace(self.DELETE_MARKER, ""))
        
        if not original_path.exists():
            # Файл уже удалён локально - удаляем из облака
            remote_path = self._get_remote_path(str(original_path), folder)
            try:
                if self.yadisk_api.exists(remote_path):
                    self.yadisk_api.remove(remote_path)
                    self.metadata.add_operation(
                        operation='delete',
                        path=str(original_path),
                        status='success',
                        size=0,
                        details='Удалено по маркеру'
                    )
                    logging.info(f"Удалено из облака по маркеру: {remote_path}")
            except Exception as e:
                logging.error(f"Ошибка удаления из облака: {e}")
                self.metadata.add_operation(
                    operation='delete',
                    path=str(original_path),
                    status='error',
                    size=0,
                    details=str(e)
                )
    
    def _handle_file_deletion(self, filepath: Path, folder: Dict):
        """Обработка удаления файла"""
        # В одностороннем режиме игнорируем локальное удаление
        if folder.get('mode') == 'one_way':
            return
        
        # В двустороннем режиме удаляем из облака
        remote_path = self._get_remote_path(str(filepath), folder)
        try:
            if self.yadisk_api.exists(remote_path):
                self.yadisk_api.remove(remote_path)
                self.metadata.add_operation(
                    operation='delete',
                    path=str(filepath),
                    status='success',
                    size=0,
                    details='Двусторонняя синхронизация'
                )
                logging.info(f"Удалено из облака при локальном удалении: {remote_path}")
        except Exception as e:
            logging.error(f"Ошибка удаления из облака: {e}")
    
    def _full_local_scan(self, folder: Dict):
        """Полная проверка локальных файлов"""
        local_path = Path(folder['local'])
        if not local_path.exists():
            logging.warning(f"Папка не найдена: {local_path}")
            return
        
        for root, dirs, files in os.walk(local_path):
            # Пропускаем служебные директории
            dirs[:] = [d for d in dirs if d not in [self.TRASH_FOLDER, '.git', '__pycache__', '.venv']]
            
            for file in files:
                if self._is_ignored_file(file):
                    continue
                
                filepath = Path(root) / file
                self._sync_file(str(filepath), folder)
    
    def _sync_file(self, filepath: str, folder: Dict):
        """Синхронизация одного файла"""
        if not self.running:
            return
        
        # Установка статуса "в процессе"
        self.sync_status[filepath] = SyncStatus.SYNCING
        
        try:
            remote_path = self._get_remote_path(filepath, folder)
            local_hash = self._get_file_hash(filepath)
            local_mtime = os.path.getmtime(filepath)
            
            # Проверка наличия файла в облаке
            cloud_meta = None
            if self.yadisk_api.exists(remote_path):
                cloud_meta = self.yadisk_api.get_meta(remote_path)
            
            # Случай 1: Файл существует и идентичен
            if cloud_meta and cloud_meta.get('md5') == local_hash:
                # Обновляем метаданные
                self.metadata.update_file_metadata(
                    filepath=filepath,
                    cloud_hash=local_hash,
                    cloud_path=remote_path,
                    last_sync=datetime.now().isoformat(),
                    status=SyncStatus.SYNCED
                )
                self.sync_status[filepath] = SyncStatus.SYNCED
                return
            
            # Случай 2: Файл изменён локально или отсутствует в облаке
            file_size = os.path.getsize(filepath)
            self.metadata.add_operation(
                operation='upload',
                path=filepath,
                status='pending',
                size=file_size,
                details='Начало загрузки'
            )
            
            # Загрузка файла
            self.yadisk_api.upload(filepath, remote_path, overwrite=True)
            
            # Обновление метаданных
            self.metadata.update_file_metadata(
                filepath=filepath,
                cloud_hash=local_hash,
                cloud_path=remote_path,
                last_sync=datetime.now().isoformat(),
                status=SyncStatus.SYNCED
            )
            self.metadata.add_operation(
                operation='upload',
                path=filepath,
                status='success',
                size=file_size,
                details='Загрузка завершена'
            )
            self.sync_status[filepath] = SyncStatus.SYNCED
            logging.info(f"Загружен файл: {filepath} -> {remote_path}")
            
                    except requests.exceptions.Timeout:
                error_msg = "Таймаут подключения к Яндекс.Диску"
                self.sync_status[filepath] = SyncStatus.ERROR
                self.metadata.add_operation(
                    operation='upload',
                    path=filepath,
                    status='error',
                    size=os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    details=error_msg
                )
                logging.error(f"Таймаут при синхронизации {filepath}: {error_msg}")

            except requests.exceptions.ConnectionError:
                error_msg = "Нет подключения к интернету"
                self.sync_status[filepath] = SyncStatus.ERROR
                self.metadata.add_operation(
                    operation='upload',
                    path=filepath,
                    status='error',
                    size=os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    details=error_msg
                )
                logging.error(f"Ошибка сети при синхронизации {filepath}: {error_msg}")

            except yadisk.exceptions.UnauthorizedError:
                error_msg = "Токен недействителен. Требуется повторная авторизация"
                self.sync_status[filepath] = SyncStatus.ERROR
                self.metadata.add_operation(
                    operation='upload',
                    path=filepath,
                    status='error',
                    size=os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    details=error_msg
                )
                logging.error(f"Ошибка авторизации при синхронизации {filepath}: {error_msg}")

            except Exception as e:
                # Универсальная обработка всех остальных ошибок
                error_msg = str(e)
                # Обрезаем слишком длинные сообщения
                if len(error_msg) > 100:
                    error_msg = error_msg[:97] + "..."
                
                self.sync_status[filepath] = SyncStatus.ERROR
                self.metadata.add_operation(
                    operation='upload',
                    path=filepath,
                    status='error',
                    size=os.path.getsize(filepath) if os.path.exists(filepath) else 0,
                    details=error_msg
                )
                logging.error(f"Ошибка синхронизации {filepath}: {error_msg}")
    
    def _check_cloud_changes(self, folder: Dict):
        """Проверка изменений в облаке для двусторонней синхронизации"""
        remote_path = folder['remote']
        local_path = Path(folder['local'])
        
        try:
            # Получаем список файлов в облаке
            cloud_items = self.yadisk_api.list_directory(remote_path)
            cloud_files = {}
            
            for item in cloud_items:
                if item['type'] == 'file':
                    # Относительный путь от корня синхронизации
                    rel_path = item['path'].replace(remote_path, '', 1).lstrip('/')
                    cloud_files[rel_path] = {
                        'md5': item.get('md5', ''),
                        'modified': item.get('modified', ''),
                        'size': item.get('size', 0)
                    }
            
            # Сравниваем с локальными файлами
            for rel_path, cloud_meta in cloud_files.items():
                local_file = local_path / rel_path
                
                # Случай 1: Новый файл в облаке
                if not local_file.exists():
                    self._download_file(folder, rel_path, cloud_meta)
                    continue
                
                # Случай 2: Файл изменён в облаке
                local_hash = self._get_file_hash(str(local_file))
                if cloud_meta['md5'] != local_hash:
                    self._handle_cloud_modification(folder, rel_path, cloud_meta, local_file)
            
            # Случай 3: Файлы удалены в облаке
            self._handle_cloud_deletions(folder, cloud_files)
            
        except Exception as e:
            logging.error(f"Ошибка проверки облака для {remote_path}: {e}")
    
    def _download_file(self, folder: Dict, rel_path: str, meta: Dict):
        """Скачивание файла из облака"""
        local_path = Path(folder['local']) / rel_path
        remote_path = f"{folder['remote'].rstrip('/')}/{rel_path}"
        
        try:
            # Создаём родительские директории
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Скачивание
            self.yadisk_api.download(remote_path, str(local_path))
            
            # Обновление метаданных
            self.metadata.update_file_metadata(
                filepath=str(local_path),
                cloud_hash=meta['md5'],
                cloud_path=remote_path,
                last_sync=datetime.now().isoformat(),
                status=SyncStatus.SYNCED
            )
            self.metadata.add_operation(
                operation='download',
                path=str(local_path),
                status='success',
                size=meta['size'],
                details='Скачан из облака'
            )
            logging.info(f"Скачан файл: {remote_path} -> {local_path}")
            
                except requests.exceptions.Timeout:
            error_msg = "Таймаут подключения к Яндекс.Диску"
            self.metadata.add_operation(
                operation='download',
                path=str(local_path),
                status='error',
                size=meta['size'],
                details=error_msg
            )
            logging.error(f"Таймаут при скачивании {rel_path}: {error_msg}")

        except requests.exceptions.ConnectionError:
            error_msg = "Нет подключения к интернету"
            self.metadata.add_operation(
                operation='download',
                path=str(local_path),
                status='error',
                size=meta['size'],
                details=error_msg
            )
            logging.error(f"Ошибка сети при скачивании {rel_path}: {error_msg}")

        except yadisk.exceptions.UnauthorizedError:
            error_msg = "Токен недействителен. Требуется повторная авторизация"
            self.metadata.add_operation(
                operation='download',
                path=str(local_path),
                status='error',
                size=meta['size'],
                details=error_msg
            )
            logging.error(f"Ошибка авторизации при скачивании {rel_path}: {error_msg}")

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:97] + "..."
            
            self.metadata.add_operation(
                operation='download',
                path=str(local_path),
                status='error',
                size=meta['size'],
                details=error_msg
            )
            logging.error(f"Ошибка скачивания {rel_path}: {error_msg}")
    
    def _handle_cloud_modification(self, folder: Dict, rel_path: str, cloud_meta: Dict, local_file: Path):
        """Обработка изменения файла в облаке при существующем локальном файле"""
        # Получаем метаданные для разрешения конфликта
        file_meta = self.metadata.get_file_metadata(str(local_file))
        local_mtime = os.path.getmtime(local_file)
        cloud_modified = cloud_meta['modified']
        
        # Если локальный файл изменялся позже последней синхронизации - конфликт
        if file_meta and file_meta.get('last_sync'):
            last_sync = datetime.fromisoformat(file_meta['last_sync'])
            local_dt = datetime.fromtimestamp(local_mtime)
            
            if local_dt > last_sync:
                # Конфликт версий - сохраняем обе версии
                self._resolve_conflict(folder, rel_path, cloud_meta, local_file)
                return
        
        # Скачиваем версию из облака (локальная версия устарела или отсутствует метаданные)
        self._download_file(folder, rel_path, cloud_meta)
    
    def _resolve_conflict(self, folder: Dict, rel_path: str, cloud_meta: Dict, local_file: Path):
        """Разрешение конфликта версий"""
        # Создаём имя для конфликтной копии локального файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        conflict_name = f"{local_file.stem}{self.CONFLICT_MARKER}{timestamp}{local_file.suffix}"
        conflict_path = local_file.parent / conflict_name
        
        try:
            # Сохраняем локальную версию
            shutil.copy2(local_file, conflict_path)
            
            # Скачиваем версию из облака поверх текущего файла
            self._download_file(folder, rel_path, cloud_meta)
            
            # Запись в историю
            self.metadata.add_operation(
                operation='conflict',
                path=str(local_file),
                status='success',
                size=cloud_meta['size'],
                details=f'Конфликт разрешён. Локальная версия сохранена как: {conflict_name}'
            )
            logging.warning(f"Конфликт разрешён для {rel_path}. Локальная версия: {conflict_name}")
            
        except Exception as e:
            self.metadata.add_operation(
                operation='conflict',
                path=str(local_file),
                status='error',
                size=cloud_meta['size'],
                details=f'Ошибка разрешения конфликта: {str(e)}'
            )
            logging.error(f"Ошибка разрешения конфликта для {rel_path}: {e}")
    
    def _handle_cloud_deletions(self, folder: Dict, cloud_files: Dict):
        """Обработка файлов, удалённых в облаке"""
        local_path = Path(folder['local'])
        
        # Собираем все локальные файлы
        local_files = []
        for root, _, files in os.walk(local_path):
            for file in files:
                if not self._is_ignored_file(file):
                    filepath = Path(root) / file
                    rel_path = filepath.relative_to(local_path).as_posix()
                    local_files.append((filepath, rel_path))
        
        # Проверяем, какие файлы отсутствуют в облаке
        for filepath, rel_path in local_files:
            if rel_path not in cloud_files:
                file_meta = self.metadata.get_file_metadata(str(filepath))
                
                # Удаляем только если файл был ранее синхронизирован
                if file_meta and file_meta.get('status') == SyncStatus.SYNCED:
                    self._move_to_trash(filepath, folder)
                    self.metadata.update_file_metadata(
                        filepath=str(filepath),
                        status=SyncStatus.SYNCED,
                        last_sync=datetime.now().isoformat()
                    )
                    self.metadata.add_operation(
                        operation='delete',
                        path=str(filepath),
                        status='success',
                        size=0,
                        details='Удалено из облака (двусторонняя синхронизация)'
                    )
    
    def _move_to_trash(self, filepath: Path, folder: Dict):
        """Перемещение файла в корзину синхронизации"""
        if not folder.get('use_trash', True):
            filepath.unlink(missing_ok=True)
            return
        
        trash_dir = Path(folder['local']) / self.TRASH_FOLDER
        trash_dir.mkdir(exist_ok=True)
        
        # Сохраняем структуру путей в корзине
        rel_path = filepath.relative_to(folder['local'])
        trash_file = trash_dir / rel_path
        trash_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Уникальное имя при конфликте
        counter = 1
        while trash_file.exists():
            trash_file = trash_dir / f"{rel_path.stem}_{counter}{rel_path.suffix}"
            counter += 1
        
        try:
            shutil.move(str(filepath), str(trash_file))
            logging.info(f"Файл перемещён в корзину: {trash_file}")
        except Exception as e:
            logging.error(f"Ошибка перемещения в корзину {filepath}: {e}")
            filepath.unlink(missing_ok=True)  # Удаляем как крайнюю меру
    
    def _get_remote_path(self, local_path: str, folder: Dict) -> str:
        """Преобразование локального пути в путь облака"""
        rel_path = os.path.relpath(local_path, folder['local']).replace("\\", "/")
        return f"{folder['remote'].rstrip('/')}/{rel_path}"
    
    def _get_file_hash(self, filepath: str) -> str:
        """Получение MD5 хеша файла"""
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logging.error(f"Ошибка хеширования {filepath}: {e}")
            return ''
    
    def _is_ignored_file(self, filename: str) -> bool:
        """Проверка, следует ли игнорировать файл"""
        ignore_patterns = [
            self.DELETE_MARKER,
            self.CONFLICT_MARKER,
            '.DS_Store',
            'Thumbs.db',
            'desktop.ini',
            '*.tmp',
            '*.temp',
            '~$*',
            '.~*',
            '*.swp',
            '*.swo',
            '__pycache__',
            '.git',
            '.idea',
            '.vscode'
        ]
        
        name_lower = filename.lower()
        for pattern in ignore_patterns:
            if pattern.endswith('*'):
                if name_lower.startswith(pattern[:-1]):
                    return True
            elif pattern.startswith('*'):
                if name_lower.endswith(pattern[1:]):
                    return True
            elif '*' in pattern:
                # Простая реализация для шаблонов с *
                base = pattern.replace('*', '')
                if base in name_lower:
                    return True
            elif pattern == filename or pattern == name_lower:
                return True
        
        return False
    
    def _update_statistics(self, folder: Dict):
        """Обновление статистики синхронизации"""
        try:
            local_path = Path(folder['local'])
            if not local_path.exists():
                return
            
            # Подсчёт файлов
            file_count = 0
            total_size = 0
            
            for root, _, files in os.walk(local_path):
                # Пропускаем корзину и служебные папки
                if self.TRASH_FOLDER in root.split(os.sep):
                    continue
                
                for file in files:
                    if not self._is_ignored_file(file):
                        filepath = Path(root) / file
                        try:
                            file_count += 1
                            total_size += filepath.stat().st_size
                        except:
                            pass
            
            # Сохранение в метаданные
            self.metadata.update_folder_statistics(
                folder_path=str(local_path),
                file_count=file_count,
                total_size=total_size
            )
            
        except Exception as e:
            logging.error(f"Ошибка обновления статистики для {folder['local']}: {e}")
    
    def get_sync_status(self, filepath: str) -> str:
        """Получение статуса синхронизации файла"""
        return self.sync_status.get(filepath, SyncStatus.SYNCED)
    
    def get_overall_status(self) -> Dict:
        """Получение общего статуса синхронизации"""
        with self._lock:
            if not self.running:
                return {'status': 'stopped', 'folders': 0, 'files_pending': 0}
            
            pending = sum(1 for status in self.sync_status.values() 
                         if status in [SyncStatus.SYNCING, SyncStatus.PENDING])
            
            return {
                'status': 'running',
                'folders': len(self.sync_folders),
                'files_pending': pending,
                'last_check': datetime.now().isoformat()
            }
