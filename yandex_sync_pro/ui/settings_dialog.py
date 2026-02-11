import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttkb
from cryptography.fernet import Fernet
import yadisk
import webbrowser
import threading
import time
from datetime import datetime
import requests
import logging
import urllib.parse

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config, save_callback):
        super().__init__(parent)
        self.title("⚙️ Настройки")
        self.geometry("650x600")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self.config = config.copy()
        self.save_callback = save_callback
        self._test_thread = None
        self._test_cancel = False
        
        self._create_widgets()
        self._load_current_settings()
    
    def _create_widgets(self):
        notebook = ttkb.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        account_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(account_frame, text="Учётная запись")
        self._create_account_tab(account_frame)
        
        sync_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(sync_frame, text="Синхронизация")
        self._create_sync_tab(sync_frame)
        
        ui_frame = ttkb.Frame(notebook, padding=15)
        notebook.add(ui_frame, text="Интерфейс")
        self._create_ui_tab(ui_frame)
        
        btn_frame = ttkb.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 15))
        
        ttkb.Button(btn_frame, text="Сохранить", 
                   command=self._save_settings, bootstyle="success", width=12).pack(side=tk.RIGHT, padx=5)
        ttkb.Button(btn_frame, text="Отмена", 
                   command=self.destroy, bootstyle="secondary", width=12).pack(side=tk.RIGHT, padx=5)
    
    def _create_account_tab(self, parent):
        ttkb.Label(parent, text="Авторизация в Яндекс.Диске", 
                  font=("Segoe UI", 14, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        auth_frame = ttkb.LabelFrame(parent, text="Способ авторизации")
        auth_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.auth_method = tk.StringVar(value="token")
        auth_inner = ttkb.Frame(auth_frame, padding=10)
        auth_inner.pack(fill=tk.X)
        
        ttkb.Radiobutton(
            auth_inner, 
            text="🔐 Вручную (ввести токен)", 
            variable=self.auth_method, 
            value="token",
            command=self._toggle_auth_method
        ).pack(anchor=tk.W, pady=3)
        
        ttkb.Radiobutton(
            auth_inner, 
            text="🌐 Через браузер (OAuth 2.0)", 
            variable=self.auth_method, 
            value="oauth",
            command=self._toggle_auth_method
        ).pack(anchor=tk.W, pady=3)
        
        ttkb.Label(
            auth_inner,
            text="Рекомендуется для безопасности и автоматического обновления токена",
            font=("Segoe UI", 8),
            foreground="#888"
        ).pack(anchor=tk.W, padx=(20, 0), pady=(0, 10))
        
        self.token_section = ttkb.Frame(parent)
        self.token_section.pack(fill=tk.X, pady=5)
        
        ttkb.Label(self.token_section, text="OAuth-токен:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        
        token_entry_frame = ttkb.Frame(self.token_section)
        token_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.token_var = tk.StringVar()
        self.token_entry = ttkb.Entry(token_entry_frame, textvariable=self.token_var, width=65, 
                                    font=("Consolas", 10), show="•")
        self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttkb.Button(
            token_entry_frame,
            text="👁️",
            command=self._toggle_token_visibility,
            bootstyle="secondary",
            width=3
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        token_btn_frame = ttkb.Frame(self.token_section)
        token_btn_frame.pack(fill=tk.X, pady=10)
        
        ttkb.Button(
            token_btn_frame, 
            text="Получить токен", 
            command=self._open_token_page,
            bootstyle="info-outline",
            width=18
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.test_btn = ttkb.Button(
            token_btn_frame, 
            text="Проверить подключение", 
            command=self._test_connection,
            bootstyle="outline-success",
            width=22
        )
        self.test_btn.pack(side=tk.LEFT)
        
        self.status_frame = ttkb.Frame(self.token_section)
        self.status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_icon = ttkb.Label(self.status_frame, text="❓", font=("Segoe UI", 16), width=2)
        self.status_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        self.status_label = ttkb.Label(self.status_frame, text="Не проверено", 
                                      bootstyle="secondary", font=("Segoe UI", 10))
        self.status_label.pack(side=tk.LEFT)
        
        ttkb.Separator(parent, bootstyle="primary").pack(fill=tk.X, pady=15)
        
        self.oauth_section = ttkb.Frame(parent)
        
        ttkb.Label(self.oauth_section, text="Client ID:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.client_id_var = tk.StringVar()
        ttkb.Entry(self.oauth_section, textvariable=self.client_id_var, width=65).pack(fill=tk.X, pady=(5, 10))
        
        ttkb.Label(self.oauth_section, text="Client Secret:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.client_secret_var = tk.StringVar()
        secret_entry = ttkb.Entry(self.oauth_section, textvariable=self.client_secret_var, width=65, show="•")
        secret_entry.pack(fill=tk.X, pady=(5, 10))
        
        oauth_btn_frame = ttkb.Frame(self.oauth_section)
        oauth_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttkb.Button(
            oauth_btn_frame,
            text="👁️ Показать/скрыть",
            command=lambda: secret_entry.config(show="" if secret_entry.cget("show") == "•" else "•"),
            bootstyle="secondary",
            width=18
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        self.oauth_validate_btn = ttkb.Button(
            oauth_btn_frame,
            text="Проверить клиентские данные",
            command=self._validate_oauth_credentials,
            bootstyle="warning-outline",
            width=25
        )
        self.oauth_validate_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.oauth_authorize_btn = ttkb.Button(
            oauth_btn_frame,
            text="🚀 Авторизоваться через браузер",
            command=self._start_oauth_flow,
            bootstyle="success",
            width=28
        )
        self.oauth_authorize_btn.pack(side=tk.LEFT)
        
        self.oauth_status = ttkb.Label(
            self.oauth_section,
            text="Статус: готов к авторизации",
            bootstyle="secondary",
            font=("Segoe UI", 9)
        )
        self.oauth_status.pack(anchor=tk.W, pady=(10, 0))
        
        ttkb.Separator(parent, bootstyle="primary").pack(fill=tk.X, pady=15)
        
        ttkb.Label(parent, text="Управление аккаунтом", 
                  font=("Segoe UI", 10, "bold"), bootstyle="warning").pack(anchor=tk.W, pady=(0, 10))
        
        ttkb.Button(parent, text="Сменить аккаунт", 
                   command=self._change_account,
                   bootstyle="danger-outline", width=25).pack(anchor=tk.W)
        
        ttkb.Label(parent, text="⚠️ При смене аккаунта все настройки синхронизации сохранятся,\n"
                               "но потребуется повторная авторизация", 
                  font=("Segoe UI", 8), foreground="#ff9900").pack(anchor=tk.W, pady=(5, 0))
        
        self.oauth_section.pack_forget()
    
    def _toggle_auth_method(self):
        if self.auth_method.get() == "token":
            self.token_section.pack(fill=tk.X, pady=5)
            self.oauth_section.pack_forget()
        else:
            self.token_section.pack_forget()
            self.oauth_section.pack(fill=tk.X, pady=5)
    
    def _toggle_token_visibility(self):
        current_show = self.token_entry.cget("show")
        self.token_entry.config(show="" if current_show == "•" else "•")
    
    def _create_sync_tab(self, parent):
        ttkb.Label(parent, text="Параметры синхронизации", 
                  font=("Segoe UI", 12, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        interval_frame = ttkb.Frame(parent)
        interval_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(interval_frame, text="Интервал полной проверки (сек):", 
                  width=35, anchor=tk.W).pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=30)
        ttkb.Spinbox(interval_frame, from_=10, to=300, increment=5, 
                    textvariable=self.interval_var, width=10).pack(side=tk.LEFT)
        
        conflict_frame = ttkb.Frame(parent)
        conflict_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(conflict_frame, text="Разрешение конфликтов:", 
                  width=35, anchor=tk.W).pack(side=tk.LEFT)
        self.conflict_var = tk.StringVar(value="rename")
        ttkb.Combobox(conflict_frame, textvariable=self.conflict_var, width=20, state="readonly",
                     values=["rename", "cloud_priority", "local_priority"]).pack(side=tk.LEFT)
        
        trash_frame = ttkb.Frame(parent)
        trash_frame.pack(fill=tk.X, pady=5)
        
        self.trash_var = tk.BooleanVar(value=True)
        ttkb.Checkbutton(trash_frame, text="Использовать корзину для удалённых файлов", 
                        variable=self.trash_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
        
        ttkb.Label(parent, text="ℹ️ Файлы, помеченные на удаление, перемещаются в папку .yd_trash\n"
                               "вместо физического удаления", 
                  font=("Segoe UI", 8), foreground="#888").pack(anchor=tk.W, pady=(5, 15))
        
        autostart_frame = ttkb.Frame(parent)
        autostart_frame.pack(fill=tk.X, pady=5)
        
        self.autostart_var = tk.BooleanVar(value=False)
        ttkb.Checkbutton(autostart_frame, text="Запускать при старте системы", 
                        variable=self.autostart_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
    
    def _create_ui_tab(self, parent):
        ttkb.Label(parent, text="Настройки интерфейса", 
                  font=("Segoe UI", 12, "bold"), bootstyle="info").pack(anchor=tk.W, pady=(0, 15))
        
        theme_frame = ttkb.Frame(parent)
        theme_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(theme_frame, text="Тема оформления:", width=25, anchor=tk.W).pack(side=tk.LEFT)
        self.theme_var = tk.StringVar(value="darkly")
        themes = ["darkly", "cosmo", "flatly", "minty", "solar", "superhero", "cyborg"]
        ttkb.Combobox(theme_frame, textvariable=self.theme_var, values=themes, 
                     width=20, state="readonly").pack(side=tk.LEFT)
        
        tray_frame = ttkb.Frame(parent)
        tray_frame.pack(fill=tk.X, pady=5)
        
        self.tray_var = tk.BooleanVar(value=True)
        ttkb.Checkbutton(tray_frame, text="Сворачивать в системный трей вместо закрытия", 
                        variable=self.tray_var, bootstyle="success-round-toggle").pack(anchor=tk.W)
        
        lang_frame = ttkb.Frame(parent)
        lang_frame.pack(fill=tk.X, pady=5)
        
        ttkb.Label(lang_frame, text="Язык интерфейса:", width=25, anchor=tk.W).pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="ru")
        ttkb.Combobox(lang_frame, textvariable=self.lang_var, values=["ru", "en"], 
                     width=20, state="readonly").pack(side=tk.LEFT)
    
    def _load_current_settings(self):
        token = self.config.get('yadisk_token', '')
        if token:
            masked = token[:8] + "•" * (len(token) - 16) + token[-8:] if len(token) > 16 else "•" * len(token)
            self.token_var.set(masked)
            self.after(100, self._test_connection)
        else:
            self.status_icon.config(text="❌", bootstyle="danger")
            self.status_label.config(text="Не авторизован", bootstyle="danger")
        
        self.client_id_var.set(self.config.get('yadisk_client_id', ''))
        self.client_secret_var.set(self.config.get('yadisk_client_secret', ''))
        
        self.interval_var.set(self.config.get('sync_interval', 30))
        self.conflict_var.set(self.config.get('conflict_resolution', 'rename'))
        self.trash_var.set(self.config.get('use_trash', True))
        self.autostart_var.set(self.config.get('autostart', False))
        self.theme_var.set(self.config.get('theme', 'darkly'))
        self.tray_var.set(self.config.get('minimize_to_tray', True))
        self.lang_var.set(self.config.get('language', 'ru'))
    
    def _open_token_page(self):
        if self.auth_method.get() == "token":
            webbrowser.open("https://yandex.ru/dev/disk/poligon/")
        else:
            if messagebox.askyesno(
                "Регистрация приложения",
                "Для использования OAuth 2.0 нужно зарегистрировать приложение в Яндексе.\n"
                "Открыть страницу регистрации?"
            ):
                webbrowser.open("https://oauth.yandex.ru/client/new")
                messagebox.showinfo(
                    "Инструкция",
                    "1. Название приложения: Yandex Disk Sync Pro\n"
                    "2. Callback URI: http://localhost:8080/callback\n"
                    "3. Права доступа: Яндекс.Диск (все разрешения)\n"
                    "4. После создания скопируйте Client ID и Client Secret\n"
                    "5. Вставьте их в соответствующие поля в настройках"
                )
    
    def _test_connection(self):
        self._test_cancel = True
        if self._test_thread and self._test_thread.is_alive():
            return

        token = self.token_var.get().strip()
        if "•" in token and 'yadisk_token' in self.config:
            token = self.config['yadisk_token']

        if not token or "•" in token:
            messagebox.showerror("Ошибка", "Введите полный OAuth-токен")
            self.status_icon.config(text="❌", bootstyle="danger")
            self.status_label.config(text="Токен не указан", bootstyle="danger")
            return

        self.test_btn.config(text="Проверка...", state="disabled", bootstyle="secondary")
        self.status_icon.config(text="⏳", bootstyle="warning")
        self.status_label.config(text="Проверка подключения...", bootstyle="warning")
        self.update()

        self._test_cancel = False

        def check_worker():
            try:
                y = yadisk.YaDisk(token=token)
                
                if self._test_cancel:
                    return

                disk_info = y.get_disk_info(timeout=10)
                
                if self._test_cancel:
                    return

                self._update_status_ui("✅", "Подключено к Яндекс.Диску", "success")
                self.config['yadisk_token'] = token

            except yadisk.exceptions.UnauthorizedError:
                if not self._test_cancel:
                    self._update_status_ui("❌", "Неверный токен", "danger")
            except yadisk.exceptions.ForbiddenError:
                if not self._test_cancel:
                    self._update_status_ui("❌", "Доступ запрещён", "danger")
            except yadisk.exceptions.TooManyRequestsError:
                if not self._test_cancel:
                    self._update_status_ui("⚠️", "Лимит запросов", "warning")
            except Exception as e:
                if not self._test_cancel:
                    error_msg = str(e)
                    if "timeout" in error_msg.lower():
                        display_msg = "Таймаут подключения"
                    elif "connection" in error_msg.lower() or "getaddrinfo" in error_msg.lower():
                        display_msg = "Нет интернета"
                    else:
                        display_msg = "Ошибка подключения"
                    self._update_status_ui("❌", display_msg, "danger")
            finally:
                if not self._test_cancel:
                    self._update_button_ui("Проверить подключение", "outline-success", "normal")

        self._test_thread = threading.Thread(target=check_worker, daemon=True, name="TokenCheck")
        self._test_thread.start()
    
    def _update_status_ui(self, icon_text, label_text, bootstyle):
        def update():
            self.status_icon.config(text=icon_text, bootstyle=bootstyle)
            self.status_label.config(text=label_text, bootstyle=bootstyle)
        self.after(0, update)
    
    def _update_button_ui(self, text, bootstyle, state):
        def update():
            self.test_btn.config(text=text, bootstyle=bootstyle, state=state)
        self.after(0, update)
    
    def _validate_oauth_credentials(self):
        client_id = self.client_id_var.get().strip()
        client_secret = self.client_secret_var.get().strip()
        
        if not client_id or not client_secret:
            messagebox.showerror("Ошибка", "Заполните оба поля: Client ID и Client Secret")
            return
        
        try:
            if not client_id or not client_secret:
                raise ValueError("Client ID и Client Secret не могут быть пустыми")
            
            if len(client_id) < 10 or len(client_secret) < 20:
                raise ValueError("Некорректный формат Client ID или Client Secret")
            
            y = yadisk.YaDisk(id=client_id, secret=client_secret)
            self.oauth_status.config(text="✅ Клиентские данные корректны", bootstyle="success")
            messagebox.showinfo("Успешно", "Клиентские данные корректны!\nТеперь нажмите 'Авторизоваться через браузер'")
            
        except Exception as e:
            self.oauth_status.config(text=f"❌ Ошибка: {str(e)}", bootstyle="danger")
            messagebox.showerror("Ошибка валидации", str(e))
    
    def _start_oauth_flow(self):
        client_id = self.client_id_var.get().strip()
        client_secret = self.client_secret_var.get().strip()
        
        if not client_id or not client_secret:
            messagebox.showerror("Ошибка", "Заполните оба поля: Client ID и Client Secret")
            return
        
        # Проверяем тип приложения по настройкам
        use_manual_flow = messagebox.askyesno(
            "Тип авторизации",
            "Использовать ручной ввод кода верификации?\n"
            "(Выберите ДА, если у вас настроено мобильное приложение)\n\n"
            "Рекомендуется: НЕТ (автоматическая авторизация через браузер)"
        )
        
        if use_manual_flow:
            self._start_manual_oauth_flow(client_id, client_secret)
        else:
            self._start_automatic_oauth_flow(client_id, client_secret)

    def _start_automatic_oauth_flow(self, client_id, client_secret):
        """Автоматическая авторизация через локальный сервер"""
        REDIRECT_URI = "http://localhost:8080/callback"
        
        self.oauth_authorize_btn.config(text="Авторизация...", state="disabled", bootstyle="secondary")
        self.oauth_status.config(text="⏳ Запуск локального сервера...", bootstyle="warning")
        self.update()
        
        def oauth_worker():
            try:
                # Запуск локального сервера
                import socket
                from http.server import HTTPServer, BaseHTTPRequestHandler
                import urllib.parse
                
                class Handler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        parsed = urllib.parse.urlparse(self.path)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'code' in params:
                            self.server.oauth_code = params['code'][0]
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html; charset=utf-8')
                            self.end_headers()
                            self.wfile.write("""
                            <!DOCTYPE html>
                            <html>
                            <head><meta charset="utf-8"><title>Успешно</title></head>
                            <body style="text-align:center;padding:50px;font-family:Arial">
                                <h1 style="color:#4CAF50">✅ Авторизация успешна!</h1>
                                <p>Можете закрыть это окно.</p>
                            </body>
                            </html>
                            """.encode('utf-8'))
                        else:
                            self.send_response(400)
                            self.end_headers()
                    
                    def log_message(self, format, *args):
                        pass
                
                # Проверка порта
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    if s.connect_ex(('localhost', 8080)) == 0:
                        raise RuntimeError("Порт 8080 занят. Закройте другие приложения, использующие этот порт.")
                
                server = HTTPServer(('localhost', 8080), Handler)
                server.oauth_code = None
                
                server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                server_thread.start()
                
                time.sleep(0.5)
                
                # Формируем URL авторизации
                auth_url = (
                    f"https://oauth.yandex.ru/authorize"
                    f"?response_type=code"
                    f"&client_id={client_id}"
                    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
                    f"&force_confirm=true"
                )
                
                self._update_oauth_status("⏳ Открытие браузера...", "warning")
                webbrowser.open(auth_url)
                
                # Ожидание кода (макс 120 сек)
                for _ in range(120):
                    if hasattr(server, 'oauth_code') and server.oauth_code:
                        break
                    time.sleep(1)
                
                code = server.oauth_code
                server.shutdown()
                server.server_close()
                
                if not code:
                    raise RuntimeError("Таймаут ожидания авторизации (120 сек)")
                
                # Получение токена
                response = requests.post(
                    "https://oauth.yandex.ru/token",
                    data={
                        'grant_type': 'authorization_code',
                        'code': code,
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'redirect_uri': REDIRECT_URI
                    },
                    timeout=10
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"Ошибка получения токена: {response.text}")
                
                token = response.json()['access_token']
                
                # Сохранение данных
                self.config['yadisk_token'] = token
                self.config['yadisk_client_id'] = client_id
                self.config['yadisk_client_secret'] = client_secret
                
                self._update_oauth_status("✅ Авторизация успешна!", "success")
                self.after(0, lambda: self._show_token_after_oauth(token))
                
            except Exception as e:
                error_msg = str(e)
                if "Порт 8080 занят" in error_msg:
                    error_msg = "Порт 8080 занят другим приложением. Закройте другие программы и попробуйте снова."
                elif "timeout" in error_msg.lower():
                    error_msg = "Таймаут подключения к Яндексу"
                elif "connection" in error_msg.lower():
                    error_msg = "Нет подключения к интернету"
                self._update_oauth_status(f"❌ Ошибка: {error_msg}", "danger")
            finally:
                self.after(0, lambda: self.oauth_authorize_btn.config(
                    text="🚀 Авторизоваться через браузер", 
                    state="normal", 
                    bootstyle="success"
                ))
        
        threading.Thread(target=oauth_worker, daemon=True, name="OAuthFlow").start()

    def _start_manual_oauth_flow(self, client_id, client_secret):
        """Ручной ввод кода верификации (для мобильных приложений)"""
        # Генерация URL авторизации
        auth_url = (
            f"https://oauth.yandex.ru/authorize"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri=https://oauth.yandex.ru/verification_code"
        )
        
        messagebox.showinfo(
            "Ручная авторизация",
            "1. Откроется страница Яндекса для авторизации\n"
            "2. Подтвердите доступ к Диску\n"
            "3. Скопируйте КОД ВЕРИФИКАЦИИ из адресной строки браузера\n"
            "4. Вставьте код в появившееся окно"
        )
        
        webbrowser.open(auth_url)
        
        # Запрос кода у пользователя
        code = simpledialog.askstring(
            "Код верификации",
            "Введите код верификации из адресной строки браузера:",
            parent=self
        )
        
        if not code:
            self.oauth_status.config(text="❌ Авторизация отменена", bootstyle="danger")
            return
        
        self.oauth_authorize_btn.config(text="Получение токена...", state="disabled", bootstyle="secondary")
        self.oauth_status.config(text="⏳ Получение токена...", bootstyle="warning")
        self.update()
        
        def token_worker():
            try:
                # Обмен кода на токен
                response = requests.post(
                    "https://oauth.yandex.ru/token",
                    data={
                        'grant_type': 'authorization_code',
                        'code': code,
                        'client_id': client_id,
                        'client_secret': client_secret,
                        'redirect_uri': 'https://oauth.yandex.ru/verification_code'
                    },
                    timeout=10
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"Ошибка получения токена: {response.text}")
                
                token = response.json()['access_token']
                
                # Сохранение данных
                self.config['yadisk_token'] = token
                self.config['yadisk_client_id'] = client_id
                self.config['yadisk_client_secret'] = client_secret
                
                self._update_oauth_status("✅ Токен получен!", "success")
                self.after(0, lambda: self._show_token_after_oauth(token))
                
            except Exception as e:
                error_msg = str(e)
                if "invalid_grant" in error_msg.lower():
                    error_msg = "Неверный код верификации или срок действия кода истёк"
                self._update_oauth_status(f"❌ Ошибка: {error_msg}", "danger")
            finally:
                self.after(0, lambda: self.oauth_authorize_btn.config(
                    text="🚀 Авторизоваться через браузер", 
                    state="normal", 
                    bootstyle="success"
                ))
        
        threading.Thread(target=token_worker, daemon=True, name="TokenExchange").start()
    
    def _update_oauth_status(self, text, bootstyle):
        def update():
            self.oauth_status.config(text=text, bootstyle=bootstyle)
        self.after(0, update)
    
    def _show_token_after_oauth(self, token):
        self.auth_method.set("token")
        self._toggle_auth_method()
        
        masked = token[:8] + "•" * (len(token) - 16) + token[-8:] if len(token) > 16 else "•" * len(token)
        self.token_var.set(masked)
        
        self.status_icon.config(text="✅", bootstyle="success")
        self.status_label.config(text="Подключено через OAuth 2.0", bootstyle="success")
        
        messagebox.showinfo(
            "Успешная авторизация", 
            "✅ Авторизация через Яндекс завершена!\n"
            "Токен доступа автоматически сохранён.\n"
            "Теперь вы можете настроить синхронизацию папок."
        )
    
    def _change_account(self):
        if messagebox.askyesno("Подтверждение", 
                             "Вы действительно хотите сменить аккаунт?\n"
                             "Текущий токен будет удалён из конфигурации."):
            self.config.pop('yadisk_token', None)
            self.config.pop('encrypted_token', None)
            self.config.pop('yadisk_client_id', None)
            self.config.pop('yadisk_client_secret', None)
            self.token_var.set("")
            self.client_id_var.set("")
            self.client_secret_var.set("")
            self._update_status_ui("❌", "Аккаунт отвязан", "danger")
            messagebox.showinfo("Успешно", "Аккаунт отвязан. Введите новые данные для подключения.")
    
    def _save_settings(self):
        if 'yadisk_token' not in self.config or not self.config['yadisk_token']:
            if not messagebox.askyesno("Предупреждение", 
                                     "Токен не установлен или недействителен.\n"
                                     "Сохранить настройки без подключения к облаку?"):
                return
        
        self.config['sync_interval'] = self.interval_var.get()
        self.config['conflict_resolution'] = self.conflict_var.get()
        self.config['use_trash'] = self.trash_var.get()
        self.config['autostart'] = self.autostart_var.get()
        self.config['theme'] = self.theme_var.get()
        self.config['minimize_to_tray'] = self.tray_var.get()
        self.config['language'] = self.lang_var.get()
        self.config['yadisk_client_id'] = self.client_id_var.get().strip()
        self.config['yadisk_client_secret'] = self.client_secret_var.get().strip()
        
        self.save_callback(self.config)
        messagebox.showinfo("Успешно", "Настройки сохранены")
        self.destroy()
