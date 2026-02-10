"""
Обёртка над yadisk с кэшированием и обработкой ошибок
"""
import time
import logging
from typing import List, Dict, Optional
import yadisk
from functools import wraps

class CloudAPIError(Exception):
    """Исключение для ошибок работы с облаком"""
    pass

def retry_on_failure(max_attempts=3, delay=2):
    """Декоратор для повторных попыток при ошибках"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(self, *args, **kwargs)
                except (yadisk.exceptions.NetworkError, 
                        yadisk.exceptions.TooManyRequestsError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logging.warning(f"Попытка {attempt + 1} не удалась для {func.__name__}: {e}")
                        time.sleep(delay * (attempt + 1))  # Экспоненциальная задержка
                    else:
                        raise CloudAPIError(f"Не удалось выполнить {func.__name__} после {max_attempts} попыток") from e
                except yadisk.exceptions.PathNotFoundError:
                    raise  # Не повторяем для несуществующих путей
                except Exception as e:
                    raise CloudAPIError(f"Ошибка в {func.__name__}: {e}") from e
            raise last_exception
        return wrapper
    return decorator

class YandexDiskAPI:
    def __init__(self):
        self.client: Optional[yadisk.YaDisk] = None
        self._cache = {}
        self._cache_ttl = 30  # TTL кэша в секундах
        self._last_request_time = 0
        self._rate_limit_delay = 0.1  # Задержка между запросами (сек)
        
        logging.info("YandexDiskAPI инициализирован")
    
    def set_token(self, token: str):
        """Установка OAuth-токена"""
        try:
            self.client = yadisk.YaDisk(token=token)
            if not self.client.check_token():
                raise CloudAPIError("Недействительный токен")
            self._cache.clear()
            logging.info("Токен Яндекс.Диска установлен")
        except Exception as e:
            raise CloudAPIError(f"Ошибка установки токена: {e}")
    
    def is_authorized(self) -> bool:
        """Проверка авторизации"""
        return self.client is not None
    
    def _enforce_rate_limit(self):
        """Ограничение частоты запросов"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _get_cache_key(self, operation: str, path: str) -> str:
        """Генерация ключа кэша"""
        return f"{operation}:{path}"
    
    def _get_cached(self, key: str) -> Optional[Dict]:
        """Получение данных из кэша"""
        if key in self._cache:
            cached = self._cache[key]
            if time.time() - cached['timestamp'] < self._cache_ttl:
                return cached['data']
            else:
                del self._cache[key]
        return None
    
    def _set_cache(self, key: str, data):
        """Сохранение данных в кэш"""
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    @retry_on_failure()
    def exists(self, path: str) -> bool:
        """Проверка существования файла/папки"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        cache_key = self._get_cache_key('exists', path)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        try:
            result = self.client.exists(path)
            self._set_cache(cache_key, result)
            return result
        except yadisk.exceptions.PathNotFoundError:
            self._set_cache(cache_key, False)
            return False
    
    @retry_on_failure()
    def get_meta(self, path: str) -> Dict:
        """Получение метаданных файла/папки"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        cache_key = self._get_cache_key('meta', path)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        try:
            meta = self.client.get_meta(path)
            result = {
                'path': meta.path,
                'type': meta.type,
                'size': getattr(meta, 'size', 0),
                'md5': getattr(meta, 'md5', ''),
                'modified': getattr(meta, 'modified', ''),
                'created': getattr(meta, 'created', '')
            }
            self._set_cache(cache_key, result)
            return result
        except yadisk.exceptions.PathNotFoundError as e:
            raise CloudAPIError(f"Путь не найден: {path}") from e
    
    @retry_on_failure()
    def list_directory(self, path: str) -> List[Dict]:
        """Получение списка файлов в директории"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        cache_key = self._get_cache_key('list', path)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        
        try:
            items = []
            for item in self.client.listdir(path):
                items.append({
                    'path': item.path,
                    'type': item.type,
                    'name': getattr(item, 'name', ''),
                    'size': getattr(item, 'size', 0),
                    'md5': getattr(item, 'md5', ''),
                    'modified': getattr(item, 'modified', '')
                })
            
            self._set_cache(cache_key, items)
            return items
        except yadisk.exceptions.PathNotFoundError as e:
            raise CloudAPIError(f"Директория не найдена: {path}") from e
    
    @retry_on_failure(max_attempts=2, delay=3)  # Меньше попыток для тяжёлых операций
    def upload(self, local_path: str, remote_path: str, overwrite: bool = True):
        """Загрузка файла в облако"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        # Очищаем кэш для родительской директории
        parent_dir = '/'.join(remote_path.rstrip('/').split('/')[:-1]) or '/'
        self._cache.pop(self._get_cache_key('list', parent_dir), None)
        
        try:
            self.client.upload(local_path, remote_path, overwrite=overwrite)
            # Очищаем кэш для загруженного файла
            self._cache.pop(self._get_cache_key('exists', remote_path), None)
            self._cache.pop(self._get_cache_key('meta', remote_path), None)
        except Exception as e:
            raise CloudAPIError(f"Ошибка загрузки {local_path} -> {remote_path}: {e}") from e
    
    @retry_on_failure(max_attempts=2, delay=3)
    def download(self, remote_path: str, local_path: str):
        """Скачивание файла из облака"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        
        try:
            self.client.download(remote_path, local_path)
        except Exception as e:
            raise CloudAPIError(f"Ошибка скачивания {remote_path} -> {local_path}: {e}") from e
    
    @retry_on_failure()
    def remove(self, path: str, permanently: bool = False):
        """Удаление файла/папки"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        # Очищаем кэш
        self._cache.clear()
        
        try:
            self.client.remove(path, permanently=permanently)
        except Exception as e:
            raise CloudAPIError(f"Ошибка удаления {path}: {e}") from e
    
    @retry_on_failure()
    def mkdir(self, path: str):
        """Создание директории"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        # Очищаем кэш для родительской директории
        parent_dir = '/'.join(path.rstrip('/').split('/')[:-1]) or '/'
        self._cache.pop(self._get_cache_key('list', parent_dir), None)
        
        try:
            self.client.mkdir(path)
        except yadisk.exceptions.DirectoryExistsError:
            pass  # Директория уже существует - не ошибка
        except Exception as e:
            raise CloudAPIError(f"Ошибка создания директории {path}: {e}") from e
    
    def clear_cache(self):
        """Очистка кэша"""
        self._cache.clear()
        logging.info("Кэш API очищен")
    
    def get_disk_info(self) -> Dict:
        """Получение информации о диске"""
        if not self.client:
            raise CloudAPIError("Не установлен клиент Яндекс.Диска")
        
        self._enforce_rate_limit()
        
        try:
            disk_info = self.client.get_disk_info()
            return {
                'total_space': disk_info.total_space,
                'used_space': disk_info.used_space,
                'system_space': disk_info.system_space,
                'trash_size': disk_info.trash_size,
                'free_space': disk_info.total_space - disk_info.used_space
            }
        except Exception as e:
            raise CloudAPIError(f"Ошибка получения информации о диске: {e}") from e
