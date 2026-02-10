"""
Основное окно приложения с вкладками и панелью управления
"""
import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from datetime import datetime
import webbrowser
import logging

# Импорт панелей
from .stats_panel import StatsPanel
from .history_panel import HistoryPanel
from .folder_manager import FolderManager
from .settings_dialog import SettingsDialog

class MainWindow:
    def __init__(self, root, sync_engine, metadata_manager, config, on_close_callback):
        self.root = root
        self.sync_engine = sync_engine
        self.metadata = metadata_manager
        self.config = config
        self.on_close_callback = on_close_callback
        
        self._create_widgets()
        self._create_menu()
        self._apply_theme(self.config.get('theme', 'darkly'))
        
        # Таймер автообновления статистики
        self._schedule_stats_update()
        
        logging.info("MainWindow инициализирован")
    
    def _create_widgets(self):
        # Верхняя панель статуса
        self.status_bar = ttkb.Frame(self.root, bootstyle="secondary")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        
        self.status_label = ttkb.Label(
            self.status_bar, 
            text="Статус: ожидание", 
            bootstyle="inverse-secondary",
            font=("Segoe UI", 9)
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.stats_label = ttkb.Label(
            self.status_bar,
            text="Файлов: 0 | Трафик сегодня: 0 МБ",
            bootstyle="inverse-secondary",
            font=("Segoe UI", 8)
        )
        self.stats_label.pack(side=tk.RIGHT, padx=10)
        
        # Панель управления (кнопки синхронизации)
        control_frame = ttkb.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Кнопки управления
        btn_frame = ttkb.Frame(control_frame)
        btn_frame.pack(side=tk.LEFT)
        
        self.start_btn = ttkb.Button(
            btn_frame, 
            text="▶️ Запустить синхронизацию", 
            command=self._start_sync,
            bootstyle=SUCCESS,
            width=22
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttkb.Button(
            btn_frame, 
            text="⏹️ Остановить", 
            command=self._stop_sync,
            bootstyle=DANGER,
            width=15,
            state=DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.resync_btn = ttkb.Button(
            btn_frame, 
            text="🔄 Полная синхронизация", 
            command=self._full_resync,
            bootstyle=WARNING,
            width=20,
            state=DISABLED
        )
        self.resync_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Индикатор активности
        self.activity_indicator = ttkb.Label(
            btn_frame,
            text="",
            font=("Segoe UI", 16),
            bootstyle=INFO
        )
        self.activity_indicator.pack(side=tk.LEFT)
        
        # Кнопка настроек
        settings_btn = ttkb.Button(
            control_frame,
            text="⚙️ Настройки",
            command=self._open_settings,
            bootstyle=SECONDARY,
            width=12
        )
        settings_btn.pack(side=tk.RIGHT)
        
        # Вкладки
        self.notebook = ttkb.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Вкладка "Синхронизация"
        self.sync_tab = FolderManager(self.notebook, self.sync_engine, self.config)
        self.notebook.add(self.sync_tab, text=" 🔄 Синхронизация")
        
        # Вкладка "Статистика"
        self.stats_tab = StatsPanel(self.notebook, self.metadata)
        self.notebook.add(self.stats_tab, text=" 📊 Статистика")
        
        # Вкладка "История"
        self.history_tab = HistoryPanel(self.notebook, self.metadata)
        self.notebook.add(self.history_tab, text=" 📜 История")
        
        # Вкладка "Журнал"
        self.log_tab = self._create_log_tab()
        self.notebook.add(self.log_tab, text=" 📝 Журнал")
        
        # Обновление состояния кнопок
        self._update_control_buttons()
    
    def _create_log_tab(self):
        """Создание вкладки журнала операций"""
        frame = ttkb.Frame(self.notebook, padding=10)
        
        # Поле для логов
        self.log_text = tk.Text(
            frame, 
            height=15, 
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#2b2b2b" if self.config.get('theme', 'darkly') == 'darkly' else "#ffffff",
            fg="#ffffff" if self.config.get('theme', 'darkly') == 'darkly' else "#000000"
        )
        log_scroll = ttkb.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки управления логами
        btn_frame = ttkb.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttkb.Button(
            btn_frame, 
            text="Очистить журнал", 
            command=self._clear_log,
            bootstyle=SECONDARY,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttkb.Button(
            btn_frame, 
            text="Сохранить в файл", 
            command=self._save_log,
            bootstyle=INFO,
            width=15
        ).pack(side=tk.LEFT)
        
        # Перехват системных логов
        self._setup_log_redirect()
        
        return frame
    
    def _setup_log_redirect(self):
        """Перенаправление системных логов в текстовое поле"""
        class LogRedirector:
            def __init__(self, text_widget, original_stream):
                self.text_widget = text_widget
                self.original_stream = original_stream
            
            def write(self, message):
                if message.strip():  # Игнорируем пустые сообщения
                    self.text_widget.insert(tk.END, message)
                    self.text_widget.see(tk.END)
                    self.original_stream.write(message)
            
            def flush(self):
                self.original_stream.flush()
        
        # Перенаправляем stdout и stderr
        import sys
        sys.stdout = LogRedirector(self.log_text, sys.__stdout__)
        sys.stderr = LogRedirector(self.log_text, sys.__stderr__)
        
        # Логируем запуск
        self._log_message(f"=== Yandex Disk Sync Pro v2.5 запущен {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    def _log_message(self, message, level="INFO"):
        """Добавление сообщения в журнал"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}\n"
        self.log_text.insert(tk.END, formatted)
        self.log_text.see(tk.END)
    
    def _create_menu(self):
        """Создание системного меню"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Меню Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Настройки", command=self._open_settings, accelerator="Ctrl+,")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._on_exit, accelerator="Alt+F4")
        
        # Меню Синхронизация
        sync_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Синхронизация", menu=sync_menu)
        sync_menu.add_command(label="Запустить", command=self._start_sync, accelerator="Ctrl+S")
        sync_menu.add_command(label="Остановить", command=self._stop_sync, accelerator="Ctrl+P")
        sync_menu.add_command(label="Полная синхронизация", command=self._full_resync, accelerator="Ctrl+R")
        sync_menu.add_separator()
        sync_menu.add_command(label="Добавить папку", command=self.sync_tab.add_folder, accelerator="Ctrl+N")
        
        # Меню Помощь
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Помощь", menu=help_menu)
        help_menu.add_command(label="Руководство пользователя", command=self._open_help)
        help_menu.add_command(label="Сообщить об ошибке", command=self._report_issue)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self._about)
        
        # Горячие клавиши
        self.root.bind("<Control-,>", lambda e: self._open_settings())
        self.root.bind("<Control-s>", lambda e: self._start_sync())
        self.root.bind("<Control-p>", lambda e: self._stop_sync())
        self.root.bind("<Control-r>", lambda e: self._full_resync())
        self.root.bind("<Control-n>", lambda e: self.sync_tab.add_folder())
        self.root.bind("<Alt-F4>", lambda e: self._on_exit())
    
    def _apply_theme(self, theme_name: str):
        """Применение темы оформления"""
        style = ttkb.Style(theme_name)
        
        # Настройка цветов текста лога в зависимости от темы
        if theme_name in ['darkly', 'superhero', 'cyborg', 'solar']:
            self.log_text.configure(bg="#2b2b2b", fg="#ffffff")
        else:
            self.log_text.configure(bg="#ffffff", fg="#000000")
        
        # Обновление конфигурации
        self.config['theme'] = theme_name
        logging.info(f"Тема изменена на: {theme_name}")
    
    def _start_sync(self):
        """Запуск синхронизации"""
        folders = self.sync_tab.get_sync_folders()
        
        if not folders:
            messagebox.showwarning(
                "Внимание", 
                "Добавьте хотя бы одну папку для синхронизации через вкладку 'Синхронизация'"
            )
            self.notebook.select(self.sync_tab)
            return
        
        if not self.sync_engine.is_running():
            # Проверка авторизации
            if not self.sync_engine.yadisk_api.is_authorized():
                messagebox.showerror(
                    "Ошибка", 
                    "Необходимо настроить подключение к Яндекс.Диску в разделе Настройки"
                )
                self._open_settings()
                return
            
            self.sync_engine.start_sync(folders)
            self._update_control_buttons()
            self._animate_activity_indicator(True)
            self.update_status("Синхронизация запущена")
            self._log_message("Синхронизация запущена", "INFO")
    
    def _stop_sync(self):
        """Остановка синхронизации"""
        if self.sync_engine.is_running():
            self.sync_engine.stop_sync()
            self._update_control_buttons()
            self._animate_activity_indicator(False)
            self.update_status("Синхронизация остановлена")
            self._log_message("Синхронизация остановлена", "INFO")
    
    def _full_resync(self):
        """Запуск полной повторной синхронизации"""
        if not self.sync_engine.is_running():
            messagebox.showwarning("Внимание", "Сначала запустите синхронизацию")
            return
        
        if messagebox.askyesno(
            "Полная синхронизация", 
            "Выполнить полную повторную проверку и синхронизацию всех файлов?\n"
            "Это может занять некоторое время."
        ):
            # Останавливаем и перезапускаем синхронизацию
            folders = self.sync_tab.get_sync_folders()
            self.sync_engine.stop_sync()
            self.sync_engine.start_sync(folders)
            self._log_message("Запущена полная повторная синхронизация", "INFO")
            messagebox.showinfo("Информация", "Полная синхронизация запущена. Следите за прогрессом в журнале.")
    
    def _open_settings(self):
        """Открытие диалога настроек"""
        # Передаём актуальный токен из движка, если он есть
        current_token = None
        if self.sync_engine.yadisk_api.is_authorized():
            # Хак для получения токена из закрытого клиента (в реальном приложении нужно хранить отдельно)
            current_token = "********"  # Маскируем токен в настройках
        
        # Создаём копию конфига для редактирования
        config_copy = self.config.copy()
        if current_token:
            config_copy['yadisk_token'] = current_token
        
        def save_callback(new_config):
            # Применяем новые настройки
            self.config.update(new_config)
            
            # Если изменилась тема - применяем
            if new_config.get('theme') != self.config.get('theme'):
                self._apply_theme(new_config['theme'])
            
            # Если включён/отключён автозапуск
            if 'autostart' in new_config:
                from core.autostart import AutostartManager
                autostart = AutostartManager()
                if new_config['autostart']:
                    autostart.enable()
                else:
                    autostart.disable()
            
            # Если установлен новый токен - обновляем клиент API
            if 'yadisk_token' in new_config and new_config['yadisk_token'] != "********":
                try:
                    self.sync_engine.yadisk_api.set_token(new_config['yadisk_token'])
                    self._log_message("Токен Яндекс.Диска обновлён", "SUCCESS")
                    messagebox.showinfo("Успешно", "Подключение к Яндекс.Диску обновлено")
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Неверный токен: {str(e)}")
                    return
            
            # Сохраняем конфиг на диск
            self._save_config()
        
        SettingsDialog(self.root, config_copy, save_callback)
    
    def _save_config(self):
        """Сохранение конфигурации на диск"""
        import json
        from pathlib import Path
        
        config_dir = Path.home() / ".ydsync_pro"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        
        # Исключаем временные данные
        safe_config = {k: v for k, v in self.config.items() 
                      if k not in ['window_size', 'last_sync']}
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(safe_config, f, indent=2, ensure_ascii=False)
        
        logging.info("Конфигурация сохранена")
    
    def _open_help(self):
        """Открытие руководства пользователя"""
        webbrowser.open("https://yandex.ru/support/disk/")
    
    def _report_issue(self):
        """Открытие страницы для сообщения об ошибке"""
        webbrowser.open("https://github.com/username/yandex-sync-pro/issues")
    
    def _about(self):
        """Диалог 'О программе'"""
        about_text = (
            f"Yandex Disk Sync Pro v2.5\n\n"
            f"Профессиональное решение для синхронизации файлов\n"
            f"с Яндекс.Диском с поддержкой двусторонней синхронизации.\n\n"
            f"© 2026 CloudSync Solutions\n"
            f"Все права защищены."
        )
        
        messagebox.showinfo("О программе", about_text)
    
    def _on_exit(self):
        """Обработчик выхода из приложения"""
        # Сохранение размера окна
        self.config['window_size'] = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        self._save_config()
        
        # Подтверждение выхода при активной синхронизации
        if self.sync_engine.is_running():
            if not messagebox.askyesno(
                "Подтверждение выхода",
                "Синхронизация сейчас активна. Вы действительно хотите выйти?\n"
                "Файлы в процессе передачи могут быть повреждены."
            ):
                return
        
        self._stop_sync()
        self.on_close_callback()
    
    def _clear_log(self):
        """Очистка журнала"""
        if messagebox.askyesno("Очистка журнала", "Очистить содержимое журнала?"):
            self.log_text.delete(1.0, tk.END)
            self._log_message("Журнал очищен", "INFO")
    
    def _save_log(self):
        """Сохранение журнала в файл"""
        from datetime import datetime
        import tkinter.filedialog as filedialog
        
        filename = f"ydsync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = filedialog.asksaveasfilename(
            initialfile=filename,
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Успешно", f"Журнал сохранён:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить журнал:\n{str(e)}")
    
    def _update_control_buttons(self):
        """Обновление состояния кнопок управления"""
        is_running = self.sync_engine.is_running()
        
        if is_running:
            self.start_btn.config(state=DISABLED, bootstyle=SECONDARY)
            self.stop_btn.config(state=NORMAL, bootstyle=DANGER)
            self.resync_btn.config(state=NORMAL, bootstyle=WARNING)
        else:
            self.start_btn.config(state=NORMAL, bootstyle=SUCCESS)
            self.stop_btn.config(state=DISABLED, bootstyle=SECONDARY)
            self.resync_btn.config(state=DISABLED, bootstyle=SECONDARY)
    
    def _animate_activity_indicator(self, active: bool):
        """Анимация индикатора активности"""
        if not hasattr(self, '_animation_id'):
            self._animation_id = None
        
        def animate():
            if not active:
                self.activity_indicator.config(text="")
                return
            
            current = self.activity_indicator.cget("text")
            frames = ["◐", "◓", "◑", "◒"]
            next_frame = frames[(frames.index(current) + 1) % len(frames)] if current in frames else frames[0]
            self.activity_indicator.config(text=next_frame)
            self._animation_id = self.root.after(100, animate)
        
        if active:
            animate()
        else:
            if self._animation_id:
                self.root.after_cancel(self._animation_id)
            self.activity_indicator.config(text="")
    
    def _schedule_stats_update(self):
        """Планирование периодического обновления статистики"""
        def update():
            if self.sync_engine.is_running():
                stats = self.metadata.get_sync_statistics()
                self.stats_label.config(text=f"Файлов: {stats['total_files']:,} | "
                                          f"Сегодня: {stats['today_files']:,} файлов")
            self.root.after(30000, update)  # Обновление каждые 30 секунд
        
        self.root.after(5000, update)  # Первое обновление через 5 секунд
    
    def update_status(self, message: str, error: bool = False):
        """Обновление статусной строки"""
        self.status_label.config(
            text=f"Статус: {message}",
            bootstyle="inverse-danger" if error else "inverse-success" if "запущена" in message else "inverse-secondary"
        )
    
    def toggle_visibility(self):
        """Переключение видимости окна (для системного трея)"""
        if self.root.state() == 'normal':
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
    
    def get_sync_folders(self):
        """Получение списка синхронизируемых папок"""
        return self.sync_tab.get_sync_folders()
