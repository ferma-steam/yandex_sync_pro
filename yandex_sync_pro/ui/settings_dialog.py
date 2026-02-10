import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttkb
from cryptography.fernet import Fernet
import yadisk
import webbrowser

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, save_callback):
        super().__init__(parent)
        self.title("⚙️ Настройки")
        self.geometry("600x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self.config = config.copy()  # Работаем с копией
        self.save_callback = save_callback
        
        self._create_widgets()
        self._load_current_settings()
    
    def _create_widgets(self):
        notebook = ttkb.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка "Учётная запись"
        account_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(account_frame, text="Учётная запись")
        self._create_account_tab(account_frame)
        
        # Вкладка "Синхронизация"
        sync_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(sync_frame, text="Синхронизация")
        self._create_sync_tab(sync_frame)
        
        # Вкладка "Интерфейс"
        ui_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(ui_frame, text="Интерфейс")
        self._create_ui_tab(ui_frame)
        
        # Кнопки внизу
        btn_frame = ttkb.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttkb.Button(btn_frame, text="Сохранить", 
                   command=self._save_settings, bootstyle="success", width=12).pack(side=tk.RIGHT, padx=5)
        ttkb.Button(btn_frame, text="Отмена", 
                   command=self.destroy, bootstyle="secondary", width=12).pack(side=tk.RIGHT, padx=5)
    
    def _create_account_tab(self, parent):
        # Заголовок
        ttkb.Label(parent, text="Подключение к Яндекс.Диску", 
                  font=("Segoe UI", 12, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        # Токен
        token_frame = ttkb.Frame(parent)
        token_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(token_frame, text="OAuth-токен:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        
        self.token_var = tk.StringVar()
        token_entry = ttkb.Entry(token_frame, textvariable=self.token_var, width=60, 
                                font=("Consolas", 10), show="•")
        token_entry.pack(fill=tk.X, pady=(5, 0))
        
        # Кнопки управления токеном
        btn_frame = ttkb.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttkb.Button(btn_frame, text="Показать/скрыть", 
                   command=lambda: token_entry.configure(show="" if token_entry.cget("show") == "•" else "•"),
                   bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttkb.Button(btn_frame, text="Получить токен", 
                   command=self._open_token_page,
                   bootstyle="info", width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        self.test_btn = ttkb.Button(btn_frame, text="Проверить подключение", 
                                   command=self._test_connection,
                                   bootstyle="outline-success", width=20)
        self.test_btn.pack(side=tk.LEFT)
        
        # Статус подключения
        self.status_label = ttkb.Label(parent, text="", bootstyle="secondary")
        self.status_label.pack(anchor=tk.W, pady=(10, 0))
        
        ttkb.Separator(parent, bootstyle="primary").pack(fill=tk.X, pady=15)
        
        # Управление аккаунтом
        ttkb.Label(parent, text="Управление аккаунтом", 
                  font=("Segoe UI", 10, "bold"), bootstyle="warning").pack(anchor=tk.W, pady=(0, 10))
        
        ttkb.Button(parent, text="Сменить аккаунт", 
                   command=self._change_account,
                   bootstyle="danger-outline", width=25).pack(anchor=tk.W)
        
        ttkb.Label(parent, text="⚠️ При смене аккаунта все настройки синхронизации будут сохранены,\n"
                               "но потребуется повторная авторизация", 
                  font=("Segoe UI", 8), foreground="#ff9900").pack(anchor=tk.W, pady=(5, 0))
    
    def _create_sync_tab(self, parent):
        ttkb.Label(parent, text="Параметры синхронизации", 
                  font=("Segoe UI", 12, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        # Интервал проверки
        interval_frame = ttkb.Frame(parent)
        interval_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(interval_frame, text="Интервал полной проверки (сек):", 
                  width=35, anchor=tk.W).pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=30)
        ttkb.Spinbox(interval_frame, from_=10, to=300, increment=5, 
                    textvariable=self.interval_var, width=10).pack(side=tk.LEFT)
        
        # Конфликты
        conflict_frame = ttkb.Frame(parent)
        conflict_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(conflict_frame, text="Разрешение конфликтов:", 
                  width=35, anchor=tk.W).pack(side=tk.LEFT)
        self.conflict_var = tk.StringVar(value="rename")
        ttkb.Combobox(conflict_frame, textvariable=self.conflict_var, width=20, state="readonly",
                     values=["rename", "cloud_priority", "local_priority"]).pack(side=tk.LEFT)
        
        # Корзина
        trash_frame = ttkb.Frame(parent)
        trash_frame.pack(fill=tk.X, pady=5)
        
        self.trash_var = tk.BooleanVar(value=True)
        ttkb.Checkbutton(trash_frame, text="Использовать корзину для удалённых файлов", 
                        variable=self.trash_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
        
        ttkb.Label(parent, text="ℹ️ Файлы, помеченные на удаление, перемещаются в папку .yd_trash\n"
                               "вместо физического удаления", 
                  font=("Segoe UI", 8), foreground="#888").pack(anchor=tk.W, pady=(5, 15))
        
        # Автозапуск
        autostart_frame = ttkb.Frame(parent)
        autostart_frame.pack(fill=tk.X, pady=5)
        
        self.autostart_var = tk.BooleanVar(value=False)
        ttkb.Checkbutton(autostart_frame, text="Запускать при старте системы", 
                        variable=self.autostart_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
    
    def _create_ui_tab(self, parent):
        ttkb.Label(parent, text="Настройки интерфейса", 
                  font=("Segoe UI", 12, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        # Тема
        theme_frame = ttkb.Frame(parent)
        theme_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(theme_frame, text="Тема оформления:", width=25, anchor=tk.W).pack(side=tk.LEFT)
        self.theme_var = tk.StringVar(value="darkly")
        themes = ["darkly", "cosmo", "flatly", "minty", "solar", "superhero", "cyborg"]
        ttkb.Combobox(theme_frame, textvariable=self.theme_var, values=themes, 
                     width=20, state="readonly").pack(side=tk.LEFT)
        
        # Сворачивание в трей
        tray_frame = ttkb.Frame(parent)
        tray_frame.pack(fill=tk.X, pady=5)
        
        self.tray_var = tk.BooleanVar(value=True)
        ttkb.Checkbutton(tray_frame, text="Сворачивать в системный трей вместо закрытия", 
                        variable=self.tray_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
        
        # Язык
        lang_frame = ttkb.Frame(parent)
        lang_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(lang_frame, text="Язык интерфейса:", width=25, anchor=tk.W).pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="ru")
        ttkb.Combobox(lang_frame, textvariable=self.lang_var, values=["ru", "en"], 
                     width=20, state="readonly").pack(side=tk.LEFT)
    
    def _load_current_settings(self):
        """Загрузка текущих настроек в форму"""
        # Токен (показываем только первые/последние символы для безопасности)
        token = self.config.get('yadisk_token', '')
        if token:
            masked = token[:8] + "•" * (len(token) - 16) + token[-8:] if len(token) > 16 else "•" * len(token)
            self.token_var.set(masked)
            self.status_label.config(text="✅ Авторизован в Яндекс.Диске", bootstyle="success")
        else:
            self.status_label.config(text="❌ Не авторизован", bootstyle="danger")
        
        # Синхронизация
        self.interval_var.set(self.config.get('sync_interval', 30))
        self.conflict_var.set(self.config.get('conflict_resolution', 'rename'))
        self.trash_var.set(self.config.get('use_trash', True))
        self.autostart_var.set(self.config.get('autostart', False))
        
        # Интерфейс
        self.theme_var.set(self.config.get('theme', 'darkly'))
        self.tray_var.set(self.config.get('minimize_to_tray', True))
        self.lang_var.set(self.config.get('language', 'ru'))
    
    def _open_token_page(self):
        """Открытие страницы получения токена"""
        webbrowser.open("https://yandex.ru/dev/disk/poligon/")
    
    def _test_connection(self):
        """Проверка подключения к Яндекс.Диску"""
        token = self.token_var.get()
        # Если токен замаскирован, пытаемся получить оригинальный из конфига
        if "•" in token and 'yadisk_token' in self.config:
            token = self.config['yadisk_token']
        
        if not token or "•" in token:
            messagebox.showerror("Ошибка", "Введите полный OAuth-токен для проверки подключения")
            return
        
        self.test_btn.config(text="Проверка...", state="disabled")
        self.update()
        
        try:
            y = yadisk.YaDisk(token=token)
            if y.check_token():
                # Получаем информацию об аккаунте
                user = y.get_user()
                self.status_label.config(
                    text=f"✅ Подключено: {user.get('display_name', 'Пользователь Яндекс')}",
                    bootstyle="success"
                )
                # Сохраняем токен во временную конфигурацию
                self.config['yadisk_token'] = token
            else:
                self.status_label.config(text="❌ Неверный токен", bootstyle="danger")
        except Exception as e:
            self.status_label.config(text=f"❌ Ошибка: {str(e)}", bootstyle="danger")
        finally:
            self.test_btn.config(text="Проверить подключение", state="normal")
    
    def _change_account(self):
        """Смена аккаунта (очистка токена)"""
        if messagebox.askyesno("Подтверждение", 
                             "Вы действительно хотите сменить аккаунт?\n"
                             "Текущий токен будет удалён из конфигурации."):
            # Удаляем токен из конфигурации
            self.config.pop('yadisk_token', None)
            self.config.pop('encrypted_token', None)
            self.token_var.set("")
            self.status_label.config(text="❌ Не авторизован", bootstyle="danger")
            messagebox.showinfo("Успешно", "Аккаунт отвязан. Введите новый токен для подключения.")
    
    def _save_settings(self):
        """Сохранение настроек"""
        # Валидация токена
        if 'yadisk_token' not in self.config or not self.config['yadisk_token']:
            if not messagebox.askyesno("Предупреждение", 
                                     "Токен не установлен или недействителен.\n"
                                     "Сохранить настройки без подключения к облаку?"):
                return
        
        # Сохранение параметров
        self.config['sync_interval'] = self.interval_var.get()
        self.config['conflict_resolution'] = self.conflict_var.get()
        self.config['use_trash'] = self.trash_var.get()
        self.config['autostart'] = self.autostart_var.get()
        self.config['theme'] = self.theme_var.get()
        self.config['minimize_to_tray'] = self.tray_var.get()
        self.config['language'] = self.lang_var.get()
        
        # Вызов коллбэка для сохранения в основном приложении
        self.save_callback(self.config)
        
        messagebox.showinfo("Успешно", "Настройки сохранены")
        self.destroy()