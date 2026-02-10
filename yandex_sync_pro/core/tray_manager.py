"""
Управление системным треем с иконками и меню
"""
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional
import logging

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
except ImportError:
    logging.warning("pystray или Pillow не установлены. Системный трей будет недоступен.")
    Icon = Menu = MenuItem = None

class TrayManager:
    def __init__(self, root_window, sync_engine, toggle_callback: Callable, exit_callback: Callable):
        self.root = root_window
        self.sync_engine = sync_engine
        self.toggle_callback = toggle_callback
        self.exit_callback = exit_callback
        self.icon: Optional[Icon] = None
        self._running = False
        
        # Создание иконок
        self.icon_image = self._create_icon(color=(30, 144, 255))  # Синяя иконка (активна)
        self.icon_inactive = self._create_icon(color=(150, 150, 150))  # Серая иконка (неактивна)
        self.icon_error = self._create_icon(color=(220, 50, 47))  # Красная иконка (ошибка)
        
        # Запуск трея в отдельном потоке
        self._start_tray()
    
    def _create_icon(self, color: tuple = (30, 144, 255)) -> Image.Image:
        """Создание иконки для системного трея"""
        # Размер иконки 64x64 для качественного масштабирования
        width, height = 64, 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        
        # Облако (круги)
        dc.ellipse((16, 20, 48, 52), fill=color + (255,))
        dc.ellipse((8, 12, 40, 44), fill=color + (255,))
        dc.ellipse((24, 8, 56, 40), fill=color + (255,))
        
        # Стрелки синхронизации
        dc.arc((20, 20, 44, 44), 0, 180, fill=(255, 255, 255), width=3)
        dc.arc((20, 20, 44, 44), 180, 360, fill=(255, 255, 255), width=3)
        
        # Стрелки
        dc.polygon([(24, 22), (20, 18), (28, 18)], fill=(255, 255, 255))  # Верхняя стрелка
        dc.polygon([(40, 42), (44, 46), (36, 46)], fill=(255, 255, 255))  # Нижняя стрелка
        
        return image
    
    def _create_menu(self) -> Menu:
        """Создание меню системного трея"""
        def on_open():
            self.toggle_callback()
        
        def on_start():
            folders = self.sync_engine.sync_folders
            if folders:
                self.sync_engine.start_sync(folders)
                self.update_icon('active')
                self.show_notification("Синхронизация запущена", "Yandex Disk Sync Pro")
        
        def on_stop():
            self.sync_engine.stop_sync()
            self.update_icon('inactive')
            self.show_notification("Синхронизация остановлена", "Yandex Disk Sync Pro")
        
        def on_exit():
            self.stop()
            self.exit_callback()
        
        def on_status():
            status = self.sync_engine.get_overall_status()
            state = status['status']
            folders = status['folders']
            pending = status['files_pending']
            
            if state == 'running':
                return f"Статус: активна ({folders} папок, {pending} файлов)"
            else:
                return "Статус: остановлена"
        
        # Динамическое меню с разделителями
        return Menu(
            MenuItem("Открыть приложение", on_open, default=True),
            Menu.SEPARATOR,
            MenuItem(on_status, lambda: None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Запустить синхронизацию", on_start,
                    enabled=lambda: not self.sync_engine.is_running()),
            MenuItem("Остановить синхронизацию", on_stop,
                    enabled=lambda: self.sync_engine.is_running()),
            Menu.SEPARATOR,
            MenuItem("Выход", on_exit)
        )
    
    def _tray_thread(self):
        """Поток системного трея"""
        if Icon is None:
            logging.error("pystray не доступен. Системный трей не будет запущен.")
            return
        
        self.icon = Icon(
            name="yandex_disk_sync_pro",
            icon=self.icon_image,
            title="Yandex Disk Sync Pro",
            menu=self._create_menu()
        )
        
        self._running = True
        logging.info("Системный трей запущен")
        
        try:
            self.icon.run()
        except Exception as e:
            logging.error(f"Ошибка работы системного трея: {e}")
        finally:
            self._running = False
    
    def _start_tray(self):
        """Запуск системного трея в отдельном потоке"""
        if sys.platform not in ['win32', 'darwin', 'linux']:
            logging.warning(f"Системный трей не поддерживается на платформе: {sys.platform}")
            return
        
        tray_thread = threading.Thread(target=self._tray_thread, daemon=True, name="SystemTray")
        tray_thread.start()
        
        # Ждём инициализации иконки
        for _ in range(10):
            if self.icon is not None:
                break
            time.sleep(0.1)
    
    def update_icon(self, state: str = 'active'):
        """
        Обновление иконки трея
        
        Args:
            state: 'active', 'inactive', 'error'
        """
        if not self.icon:
            return
        
        if state == 'active':
            icon = self.icon_image
        elif state == 'inactive':
            icon = self.icon_inactive
        else:  # error
            icon = self.icon_error
        
        # Обновление иконки (специфично для разных ОС)
        try:
            self.icon.icon = icon
            if hasattr(self.icon, 'update_menu'):
                self.icon.update_menu()
        except Exception as e:
            logging.debug(f"Ошибка обновления иконки трея: {e}")
    
    def show_notification(self, message: str, title: str = "Yandex Disk Sync Pro"):
        """Показ уведомления через системный трей"""
        if not self.icon:
            return
        
        try:
            # pystray поддерживает уведомления только в Windows и Linux (с ограничениями)
            if sys.platform == 'win32':
                self.icon.notify(message, title)
            else:
                logging.debug(f"Уведомление: [{title}] {message}")
        except Exception as e:
            logging.debug(f"Ошибка показа уведомления: {e}")
    
    def stop(self):
        """Остановка системного трея"""
        if self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                logging.debug(f"Ошибка остановки трея: {e}")
            finally:
                self.icon = None
                self._running = False
    
    def is_running(self) -> bool:
        """Проверка работы системного трея"""
        return self._running and self.icon is not None