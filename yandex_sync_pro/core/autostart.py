"""
Управление автозапуском приложения в Windows
"""
import sys
import os
from pathlib import Path
import logging

class AutostartManager:
    def __init__(self):
        self.enabled = False
        self.method = None  # 'registry' или 'startup_folder'
        
        if sys.platform == "win32":
            self._detect_current_method()
        else:
            logging.warning("Автозапуск поддерживается только в Windows")
    
    def _detect_current_method(self):
        """Определение текущего метода автозапуска"""
        # Проверка реестра
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            )
            try:
                value, _ = winreg.QueryValueEx(key, "YandexDiskSyncPro")
                if value:
                    self.enabled = True
                    self.method = 'registry'
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except ImportError:
            pass
        except Exception as e:
            logging.debug(f"Ошибка проверки реестра: {e}")
        
        # Если не найдено в реестре, проверяем папку автозагрузки
        if not self.enabled:
            startup_path = Path(os.environ.get('APPDATA', '')) / r"Microsoft\Windows\Start Menu\Programs\Startup"
            shortcut_path = startup_path / "YandexDiskSyncPro.lnk"
            
            if shortcut_path.exists():
                self.enabled = True
                self.method = 'startup_folder'
    
    def enable(self, method: str = 'registry') -> bool:
        """
        Включение автозапуска
        
        Args:
            method: 'registry' (через реестр) или 'startup_folder' (через ярлык)
        """
        if sys.platform != "win32":
            return False
        
        try:
            if method == 'registry':
                return self._enable_registry()
            elif method == 'startup_folder':
                return self._enable_startup_folder()
            else:
                raise ValueError(f"Неизвестный метод автозапуска: {method}")
        except Exception as e:
            logging.error(f"Ошибка включения автозапуска ({method}): {e}")
            return False
    
    def _enable_registry(self) -> bool:
        """Включение автозапуска через реестр Windows"""
        try:
            import winreg
            
            # Определяем путь к исполняемому файлу
            if getattr(sys, 'frozen', False):
                # PyInstaller
                exe_path = sys.executable
            else:
                # Скрипт Python
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                exe_path = f'"{exe_path}" "{script_path}"'
            
            # Добавляем аргумент для фонового режима
            full_path = f'{exe_path} --autostart'
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "YandexDiskSyncPro", 0, winreg.REG_SZ, full_path)
            winreg.CloseKey(key)
            
            self.enabled = True
            self.method = 'registry'
            logging.info(f"Автозапуск включён через реестр: {full_path}")
            return True
            
        except ImportError:
            logging.error("Модуль winreg недоступен")
            return False
        except Exception as e:
            logging.error(f"Ошибка записи в реестр: {e}")
            return False
    
    def _enable_startup_folder(self) -> bool:
        """Включение автозапуска через ярлык в папке Startup"""
        try:
            import winshell
            from win32com.client import Dispatch
            
            # Путь к папке автозагрузки
            startup_path = Path(winshell.startup())
            shortcut_path = startup_path / "YandexDiskSyncPro.lnk"
            
            # Путь к исполняемому файлу
            if getattr(sys, 'frozen', False):
                target = sys.executable
            else:
                target = sys.executable
                arguments = f'"{os.path.abspath(sys.argv[0])}" --autostart'
            
            # Создание ярлыка
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.Targetpath = target
            
            if not getattr(sys, 'frozen', False):
                shortcut.Arguments = arguments
            
            shortcut.WorkingDirectory = str(Path(target).parent)
            shortcut.IconLocation = target
            shortcut.Description = "Yandex Disk Sync Pro - Автозапуск"
            shortcut.save()
            
            self.enabled = True
            self.method = 'startup_folder'
            logging.info(f"Автозапуск включён через ярлык: {shortcut_path}")
            return True
            
        except ImportError:
            logging.error("Требуются модули winshell и pywin32 для создания ярлыка")
            return False
        except Exception as e:
            logging.error(f"Ошибка создания ярлыка автозапуска: {e}")
            return False
    
    def disable(self) -> bool:
        """Отключение автозапуска любым доступным методом"""
        if sys.platform != "win32":
            return False
        
        success = False
        
        # Удаление из реестра
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE
            )
            try:
                winreg.DeleteValue(key, "YandexDiskSyncPro")
                success = True
                logging.info("Автозапуск удалён из реестра")
            except FileNotFoundError:
                pass  # Значение не существует - не ошибка
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logging.debug(f"Ошибка удаления из реестра: {e}")
        
        # Удаление ярлыка
        try:
            import winshell
            startup_path = Path(winshell.startup())
            shortcut_path = startup_path / "YandexDiskSyncPro.lnk"
            
            if shortcut_path.exists():
                shortcut_path.unlink()
                success = True
                logging.info(f"Ярлык автозапуска удалён: {shortcut_path}")
        except Exception as e:
            logging.debug(f"Ошибка удаления ярлыка: {e}")
        
        self.enabled = False
        self.method = None
        return success or not self.enabled  # Успешно, если отключено хотя бы одним методом
    
    def is_enabled(self) -> bool:
        """Проверка состояния автозапуска"""
        self._detect_current_method()
        return self.enabled
    
    def get_method(self) -> Optional[str]:
        """Получение текущего метода автозапуска"""
        return self.method
