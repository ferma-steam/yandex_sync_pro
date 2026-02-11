#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yandex Disk Sync Pro - Professional Cloud Sync Solution
Features: System Tray, Analytics, History, Secure API Management
"""

import sys
import os
import json
import threading
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
import time  # Added missing import
import yadisk

# Import GUI modules conditionally
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    tk = None
    ttk = None
    messagebox = None
    ttkb = None

# Подключаем модули
from core.sync_engine import SyncEngine
from core.tray_manager import TrayManager
from core.autostart import AutostartManager
from core.metadata import MetadataManager
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog

# Конфигурация
APP_NAME = "Yandex Disk Sync Pro"
APP_VERSION = "2.5"
CONFIG_DIR = Path.home() / ".ydsync_pro"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "app.log"
DB_FILE = CONFIG_DIR / "history.db"

class YandexSyncPro:
    def __init__(self, autostart_mode=False):
        self.autostart_mode = autostart_mode
        self._init_directories()
        self._init_logging()
        
        # Инициализация компонентов
        self.metadata = MetadataManager(DB_FILE)
        self.sync_engine = SyncEngine(self.metadata)
        self.autostart = AutostartManager()
        self.tray = None
        
        # Загрузка конфигурации
        self.config = self._load_config()
        
        # Проверка авторизации
        if not self._check_authorization():
            if not autostart_mode:
                self._show_auth_dialog()
            else:
                logging.warning("Автозапуск отменён: нет действительного токена")
                sys.exit(0)
        
        # Запуск в режиме автозапуска (фоновый режим)
        if autostart_mode:
            self._start_background_mode()
        else:
            self._start_gui_mode()
    
    def _init_directories(self):
        """Создание рабочих директорий"""
        CONFIG_DIR.mkdir(exist_ok=True)
    
    def _init_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)-8s | %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logging.info(f"=== {APP_NAME} v{APP_VERSION} ЗАПУЩЕН ===")
    
    def _load_config(self):
        """Загрузка конфигурации с расшифровкой токена"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    raw_config = json.load(f)
                
                # Расшифровка токена если зашифрован
                if 'encrypted_token' in raw_config:
                    from cryptography.fernet import Fernet
                    key = self._get_encryption_key()
                    fernet = Fernet(key)
                    token = fernet.decrypt(raw_config['encrypted_token'].encode()).decode()
                    raw_config['yadisk_token'] = token
                
                return raw_config
            except Exception as e:
                logging.error(f"Ошибка загрузки конфигурации: {e}")
        
        return {
            'sync_folders': [],
            'autostart': False,
            'theme': 'darkly',
            'window_size': '1000x650',
            'last_sync': None
        }
    
    def _save_config(self):
        """Сохранение конфигурации с шифрованием токена"""
        # Шифрование токена
        if 'yadisk_token' in self.config:
            from cryptography.fernet import Fernet
            key = self._get_encryption_key()
            fernet = Fernet(key)
            encrypted = fernet.encrypt(self.config['yadisk_token'].encode()).decode()
            
            # Сохраняем зашифрованную версию, удаляем открытый токен
            safe_config = {k: v for k, v in self.config.items() if k != 'yadisk_token'}
            safe_config['encrypted_token'] = encrypted
        else:
            safe_config = self.config
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(safe_config, f, indent=2, ensure_ascii=False)
    
    def _get_encryption_key(self):
        """Генерация/загрузка ключа шифрования"""
        key_file = CONFIG_DIR / ".key"
        if key_file.exists():
            return key_file.read_bytes()
        else:
            from cryptography.fernet import Fernet
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            key_file.chmod(0o600)  # Только владелец может читать
            return key
    
    def _check_authorization(self):
        """Проверка действительности токена"""
        token = self.config.get('yadisk_token') or self.config.get('encrypted_token')
        if not token:
            return False
        
        try:
            # Для зашифрованного токена расшифровываем временно
            if 'encrypted_token' in self.config and 'yadisk_token' not in self.config:
                from cryptography.fernet import Fernet
                key = self._get_encryption_key()
                fernet = Fernet(key)
                token = fernet.decrypt(self.config['encrypted_token'].encode()).decode()
            
            y = yadisk.YaDisk(token=token)
            return y.check_token()
        except Exception as e:
            logging.warning(f"Токен недействителен: {e}")
            return False
    
    def _show_auth_dialog(self):
        """Диалог авторизации с валидацией"""
        if not GUI_AVAILABLE:
            logging.error("GUI недоступен - отсутствует tkinter или ttkbootstrap")
            print("❌ GUI недоступен - невозможно показать диалог авторизации")
            sys.exit(1)
            
        root = ttkb.Window(themename="darkly")
        root.title(f"🔐 {APP_NAME} - Авторизация")
        root.geometry("550x400")
        root.resizable(False, False)
        
        # Иконка
        try:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                root.iconbitmap(icon_path)
        except:
            pass
        
        ttkb.Label(root, text="Подключение к Яндекс.Диску", 
                  font=("Segoe UI", 16, "bold"), bootstyle="info").pack(pady=20)
        
        ttkb.Label(root, text="Введите OAuth-токен:", 
                  font=("Segoe UI", 10)).pack()
        
        token_var = tk.StringVar()
        token_entry = ttkb.Entry(root, textvariable=token_var, width=60, font=("Consolas", 10))
        token_entry.pack(pady=10, padx=20)
        
        # Подсказка как получить токен
        hint_frame = ttkb.Frame(root)
        hint_frame.pack(fill=X, padx=20, pady=5)
        
        ttkb.Label(hint_frame, text="ℹ️ Как получить токен:", 
                  bootstyle="warning", font=("Segoe UI", 9, "bold")).pack(anchor=W)
        ttkb.Label(hint_frame, text="1. Перейдите в Полигон Яндекс.Диска", 
                  font=("Segoe UI", 9)).pack(anchor=W)
        ttkb.Label(hint_frame, text="2. Выберите «Получить токен OAuth»", 
                  font=("Segoe UI", 9)).pack(anchor=W)
        ttkb.Label(hint_frame, text="3. Скопируйте токен из адресной строки браузера", 
                  font=("Segoe UI", 9)).pack(anchor=W)
        
        status_label = ttkb.Label(root, text="", bootstyle="secondary")
        status_label.pack(pady=5)
        
        def verify_token():
            token = token_var.get().strip()
            if not token:
                status_label.config(text="❌ Введите токен!", bootstyle="danger")
                return
            
            status_label.config(text="Проверка токена...", bootstyle="info")
            root.update()
            
            try:
                y = yadisk.YaDisk(token=token)
                if y.check_token():
                    # Сохраняем токен в конфиг
                    self.config['yadisk_token'] = token
                    self._save_config()
                    
                    status_label.config(text="✅ Токен действителен!", bootstyle="success")
                    root.update()
                    root.after(500, root.destroy)
                else:
                    status_label.config(text="❌ Неверный токен! Проверьте и попробуйте снова.", 
                                      bootstyle="danger")
            except Exception as e:
                status_label.config(text=f"❌ Ошибка: {str(e)}", bootstyle="danger")
        
        btn_frame = ttkb.Frame(root)
        btn_frame.pack(pady=15)
        
        ttkb.Button(btn_frame, text="Подключиться", 
                   command=verify_token, bootstyle="success", width=15).pack(side=LEFT, padx=5)
        ttkb.Button(btn_frame, text="Выход", 
                   command=lambda: sys.exit(0), bootstyle="secondary", width=10).pack(side=LEFT, padx=5)
        
        # Горячая клавиша Enter
        token_entry.bind("<Return>", lambda e: verify_token())
        
        root.mainloop()
    
    def _start_gui_mode(self):
        """Запуск полноценного GUI"""
        if not GUI_AVAILABLE:
            logging.error("GUI недоступен - отсутствует tkinter или ttkbootstrap")
            print("❌ GUI недоступен - установите tkinter и ttkbootstrap")
            sys.exit(1)
            
        self.root = ttkb.Window(themename=self.config.get('theme', 'darkly'))
        self.root.title(f"☁️ {APP_NAME} v{APP_VERSION}")
        self.root.geometry(self.config.get('window_size', '1000x650'))
        self.root.minsize(900, 600)
        
        # Иконка приложения
        try:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(icon_path)
        except:
            pass
        
        # Инициализация основного окна
        self.main_window = MainWindow(
            self.root, 
            self.sync_engine, 
            self.metadata,
            self.config,
            self._on_close
        )
        
        # Инициализация системного трея
        self.tray = TrayManager(
            self.root,
            self.sync_engine,
            self.main_window.toggle_visibility,
            self._on_tray_exit
        )
        
        # Восстановление состояния автозапуска
        if self.config.get('autostart', False):
            self.autostart.enable()
        
        # Запуск синхронизации если было активно ранее
        if self.config.get('last_sync'):
            self.sync_engine.start_sync(self.config['sync_folders'])
            self.main_window.update_status("Синхронизация запущена")
        
        # Обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        logging.info("GUI режим запущен")
        self.root.mainloop()
    
    def _start_background_mode(self):
        """Запуск в фоновом режиме (автозапуск)"""
        logging.info("Фоновый режим запущен (автозапуск)")
        
        # Инициализация трея без основного окна
        import pystray
        from PIL import Image, ImageDraw
        
        # Создаём простую иконку для трея
        def create_image():
            width, height = 64, 64
            image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            dc = ImageDraw.Draw(image)
            dc.ellipse((16, 16, 48, 48), fill=(30, 144, 255), outline=(0, 0, 0))
            dc.text((24, 24), "YD", fill=(255, 255, 255))
            return image
        
        # Меню трея
        menu = pystray.Menu(
            pystray.MenuItem("Открыть приложение", self._show_main_window),
            pystray.MenuItem("Запустить синхронизацию", self._start_sync_from_tray),
            pystray.MenuItem("Остановить синхронизацию", self._stop_sync_from_tray),
            pystray.MenuSeparator(),
            pystray.MenuItem("Выход", self._on_tray_exit)
        )
        
        self.tray_icon = pystray.Icon(
            "yandex_sync_pro",
            icon=create_image(),
            title=APP_NAME,
            menu=menu
        )
        
        # Запуск синхронизации
        if self.config.get('sync_folders'):
            self.sync_engine.start_sync(self.config['sync_folders'])
            logging.info("Синхронизация запущена в фоновом режиме")
        
        # Запуск иконки трея в отдельном потоке
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        # Основной цикл фонового режима
        try:
            while True:
                time.sleep(60)  # Проверка каждую минуту
        except KeyboardInterrupt:
            self._on_tray_exit()
    
    def _show_main_window(self):
        """Показать основное окно из трея"""
        if not hasattr(self, 'root') or not self.root:
            self._start_gui_mode()
        else:
            self.root.deiconify()
            self.root.lift()
    
    def _start_sync_from_tray(self):
        """Запуск синхронизации из трея"""
        if self.config.get('sync_folders'):
            self.sync_engine.start_sync(self.config['sync_folders'])
            if hasattr(self, 'tray_icon'):
                self.tray_icon.notify("Синхронизация запущена", "Yandex Disk Sync")
    
    def _stop_sync_from_tray(self):
        """Остановка синхронизации из трея"""
        self.sync_engine.stop_sync()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.notify("Синхронизация остановлена", "Yandex Disk Sync")
    
    def _on_close(self):
        """Обработчик закрытия окна - сворачивание в трей"""
        if messagebox.askyesno("Свернуть в трей?", 
                             "Свернуть приложение в системный трей вместо закрытия?\n"
                             "Синхронизация продолжит работу в фоне."):
            self.root.withdraw()  # Скрываем окно
            if self.tray:
                self.tray.show_notification("Приложение свёрнуто в трей", "Синхронизация активна")
        else:
            self._on_exit()
    
    def _on_tray_exit(self):
        """Полный выход из приложения через трей"""
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self._on_exit()
    
    def _on_exit(self):
        """Корректное завершение работы"""
        logging.info("Завершение работы приложения...")
        
        # Сохранение состояния
        self.config['window_size'] = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        self.config['autostart'] = self.autostart.is_enabled()
        self.config['last_sync'] = datetime.now().isoformat() if self.sync_engine.is_running() else None
        self._save_config()
        
        # Остановка синхронизации
        self.sync_engine.stop_sync()
        
        # Закрытие соединений
        self.metadata.close()
        
        logging.info("=== ПРИЛОЖЕНИЕ ЗАВЕРШЕНО ===")
        self.root.destroy()
        sys.exit(0)

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    # Обработка аргументов командной строки
    autostart_mode = "--autostart" in sys.argv or "-a" in sys.argv
    
    # Проверка зависимостей
    required_packages = [
        ('yadisk', 'yadisk'),
        ('watchdog', 'watchdog'),
        ('ttkbootstrap', 'ttkbootstrap'),
        ('pystray', 'pystray'),
        ('Pillow', 'PIL'),  # ВАЖНО: пакет называется Pillow, но импортируется как PIL
        ('cryptography', 'cryptography'),
        ('matplotlib', 'matplotlib'),
        ('numpy', 'numpy')
    ]
    missing = []
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        print(f"❌ Отсутствуют необходимые пакеты: {', '.join(missing)}")
        print("Установите зависимости: pip install -r requirements.txt")
        sys.exit(1)
    
    # Запуск приложения
    app = YandexSyncPro(autostart_mode=autostart_mode)