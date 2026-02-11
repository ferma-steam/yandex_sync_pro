"""
Управление авторизацией через OAuth 2.0 для Яндекс.Диска
"""
import threading
import webbrowser
import socket
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import yadisk
import logging
from typing import Optional, Tuple

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Обработчик обратного вызова OAuth"""
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        # Извлекаем код авторизации
        if 'code' in query_params:
            self.server.oauth_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Авторизация успешна</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f8ff; }
                    .success { color: #4CAF50; font-size: 24px; margin: 20px 0; }
                    p { color: #555; font-size: 16px; }
                </style>
            </head>
            <body>
                <div class="success">✅ Авторизация успешна!</div>
                <p>Вы можете закрыть это окно и вернуться в приложение.</p>
            </body>
            </html>
            """.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Ошибка авторизации")
    
    def log_message(self, format, *args):
        # Подавляем логи сервера в консоль
        pass

class OAuthManager:
    """Менеджер OAuth 2.0 авторизации"""
    AUTH_URL = "https://oauth.yandex.ru/authorize"
    TOKEN_URL = "https://oauth.yandex.ru/token"
    REDIRECT_URI = "http://localhost:8080/callback"
    
    def __init__(self):
        self.client_id: Optional[str] = None
        self.client_secret: Optional[str] = None
        self.oauth_code: Optional[str] = None
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
    
    def start_local_server(self) -> bool:
        """Запуск локального сервера для перехвата OAuth кода"""
        try:
            # Проверяем доступность порта
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', 8080)) == 0:
                    logging.warning("Порт 8080 занят. Попытка освободить...")
                    return False
            
            self.server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)
            self.server.oauth_code = None
            
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
                name="OAuthCallbackServer"
            )
            self.server_thread.start()
            
            # Ждём запуска сервера
            for _ in range(10):
                if self.server_thread.is_alive():
                    break
                threading.Event().wait(0.1)
            
            logging.info("Локальный сервер OAuth запущен на http://localhost:8080")
            return True
            
        except Exception as e:
            logging.error(f"Ошибка запуска локального сервера: {e}")
            return False
    
    def stop_local_server(self):
        """Остановка локального сервера"""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
                logging.info("Локальный сервер OAuth остановлен")
            except Exception as e:
                logging.debug(f"Ошибка остановки сервера: {e}")
            finally:
                self.server = None
                self.server_thread = None
    
    def get_auth_url(self, client_id: str) -> str:
        """Генерация URL для авторизации"""
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': self.REDIRECT_URI,
            'force_confirm': 'true'
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    def get_token(self, client_id: str, client_secret: str, code: str) -> Optional[str]:
        """Обмен кода авторизации на токен доступа"""
        try:
            y = yadisk.YaDisk(id=client_id, secret=client_secret)
            token = y.get_token(code, self.REDIRECT_URI)
            return token
        except Exception as e:
            logging.error(f"Ошибка получения токена: {e}")
            return None
    
    def authorize(self, client_id: str, client_secret: str) -> Optional[str]:
        """
        Полный цикл авторизации через браузер
        
        Возвращает:
            Токен доступа или None при ошибке
        """
        self.client_id = client_id
        self.client_secret = client_secret
        
        # 1. Запуск локального сервера
        if not self.start_local_server():
            return None
        
        try:
            # 2. Генерация и открытие URL авторизации
            auth_url = self.get_auth_url(client_id)
            logging.info(f"Открытие страницы авторизации: {auth_url}")
            
            # Открываем браузер с задержкой для гарантии запуска сервера
            threading.Event().wait(0.5)
            webbrowser.open(auth_url)
            
            # 3. Ожидание кода авторизации (максимум 120 секунд)
            for _ in range(120):
                if hasattr(self.server, 'oauth_code') and self.server.oauth_code:
                    self.oauth_code = self.server.oauth_code
                    break
                threading.Event().wait(1.0)
            
            if not self.oauth_code:
                logging.warning("Таймаут ожидания кода авторизации")
                return None
            
            # 4. Обмен кода на токен
            token = self.get_token(client_id, client_secret, self.oauth_code)
            
            if token:
                logging.info("OAuth авторизация успешна")
                return token
            else:
                logging.error("Не удалось получить токен доступа")
                return None
                
        finally:
            # 5. Остановка сервера в любом случае
            self.stop_local_server()
    
    def validate_credentials(self, client_id: str, client_secret: str) -> Tuple[bool, str]:
        """
        Валидация клиентских данных без полной авторизации
        
        Возвращает:
            (успешно, сообщение)
        """
        try:
            # Простая проверка формата
            if not client_id or not client_secret:
                return False, "Client ID и Client Secret не могут быть пустыми"
            
            if len(client_id) < 10 or len(client_secret) < 20:
                return False, "Некорректный формат Client ID или Client Secret"
            
            # Попытка создания клиента (не требует сети)
            y = yadisk.YaDisk(id=client_id, secret=client_secret)
            return True, "Клиентские данные корректны"
            
        except Exception as e:
            return False, f"Ошибка валидации: {str(e)}"
