"""
Компонент управления синхронизируемыми папками с таблицей и действиями
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from pathlib import Path
import os
import logging

class FolderManager(ttkb.Frame):
    def __init__(self, parent, sync_engine, config):
        super().__init__(parent, padding=10)
        self.sync_engine = sync_engine
        self.config = config
        self.sync_folders = config.get('sync_folders', [])
        
        self._create_widgets()
        self._load_folders()
        
        logging.info("FolderManager инициализирован")
    
    def _create_widgets(self):
        # Панель действий
        action_frame = ttkb.Frame(self)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttkb.Button(
            action_frame,
            text="➕ Добавить папку",
            command=self.add_folder,
            bootstyle=SUCCESS,
            width=18
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.edit_btn = ttkb.Button(
            action_frame,
            text="✏️ Редактировать",
            command=self._edit_folder,
            bootstyle=INFO,
            width=15,
            state=DISABLED
        )
        self.edit_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.remove_btn = ttkb.Button(
            action_frame,
            text="🗑️ Удалить",
            command=self._remove_folder,
            bootstyle=DANGER,
            width=12,
            state=DISABLED
        )
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        ttkb.Button(
            action_frame,
            text="🗁 Открыть папку",
            command=self._open_folder,
            bootstyle=SECONDARY,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttkb.Button(
            action_frame,
            text="☁️ Открыть в облаке",
            command=self._open_cloud,
            bootstyle=SECONDARY,
            width=18
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        # Поиск
        ttkb.Label(action_frame, text="Поиск:").pack(side=tk.LEFT, padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_folders)
        ttkb.Entry(
            action_frame,
            textvariable=self.search_var,
            width=30
        ).pack(side=tk.LEFT)
        
        # Таблица папок
        table_frame = ttkb.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("local", "remote", "mode", "status", "files", "size")
        self.tree = ttkb.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=12,
            selectmode="browse"
        )
        
        # Настройка колонок
        self.tree.heading("local", text="Локальная папка", anchor=tk.W)
        self.tree.heading("remote", text="Папка в облаке", anchor=tk.W)
        self.tree.heading("mode", text="Режим", anchor=tk.CENTER)
        self.tree.heading("status", text="Статус", anchor=tk.CENTER)
        self.tree.heading("files", text="Файлов", anchor=tk.E)
        self.tree.heading("size", text="Размер", anchor=tk.E)
        
        self.tree.column("local", width=350, anchor=tk.W)
        self.tree.column("remote", width=250, anchor=tk.W)
        self.tree.column("mode", width=120, anchor=tk.CENTER)
        self.tree.column("status", width=100, anchor=tk.CENTER)
        self.tree.column("files", width=80, anchor=tk.E)
        self.tree.column("size", width=100, anchor=tk.E)
        
        # Стилизация статусов
        self.tree.tag_configure("synced", background="#2e7d32", foreground="white")
        self.tree.tag_configure("syncing", background="#f57c00", foreground="white")
        self.tree.tag_configure("error", background="#c62828", foreground="white")
        self.tree.tag_configure("paused", background="#1e88e5", foreground="white")
        
        # Скроллбары
        vsb = ttkb.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttkb.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Обработчики событий
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)
        
        # Контекстное меню
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Редактировать папку", command=self._edit_folder)
        self.context_menu.add_command(label="Удалить папку", command=self._remove_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Открыть локальную папку", command=self._open_folder)
        self.context_menu.add_command(label="Открыть в Яндекс.Диске", command=self._open_cloud)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Пометить файл на удаление в облаке", command=self._mark_for_delete)
        self.context_menu.add_command(label="Очистить корзину синхронизации", command=self._empty_trash)
    
    def _on_select(self, event):
        """Обработчик выбора строки в таблице"""
        selected = self.tree.selection()
        has_selection = len(selected) > 0
        
        self.edit_btn.config(state=NORMAL if has_selection else DISABLED)
        self.remove_btn.config(state=NORMAL if has_selection else DISABLED)
    
    def _on_double_click(self, event):
        """Обработчик двойного клика - редактирование"""
        self._edit_folder()
    
    def _show_context_menu(self, event):
        """Показ контекстного меню"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def _filter_folders(self, *args):
        """Фильтрация папок по поисковому запросу"""
        query = self.search_var.get().lower()
        self.tree.delete(*self.tree.get_children())
        
        for folder in self.sync_folders:
            if (query in folder['local'].lower() or 
                query in folder['remote'].lower() or
                query in folder.get('mode', '').lower()):
                self._insert_folder_row(folder)
    
    def _insert_folder_row(self, folder: dict):
        """Вставка строки папки в таблицу"""
        # Получение статистики папки
        try:
            local_path = Path(folder['local'])
            if local_path.exists():
                file_count = sum(len(files) for _, _, files in os.walk(local_path) 
                               if '.yd_trash' not in _)
                total_size = sum(os.path.getsize(os.path.join(root, f)) 
                               for root, _, files in os.walk(local_path)
                               for f in files if '.yd_trash' not in root)
                size_str = self._format_size(total_size)
            else:
                file_count = 0
                size_str = "—"
        except Exception as e:
            logging.debug(f"Ошибка получения статистики для {folder['local']}: {e}")
            file_count = 0
            size_str = "—"
        
        # Определение статуса
        status = "✅ Синхронизировано"
        status_tag = "synced"
        
        if not Path(folder['local']).exists():
            status = "❌ Папка не найдена"
            status_tag = "error"
        elif not self.sync_engine.is_running():
            status = "⏸️ Остановлена"
            status_tag = "paused"
        
        # Определение режима
        mode_text = "➡️ Односторонняя" if folder.get('mode') == 'one_way' else "🔄 Двусторонняя"
        
        # Вставка строки
        self.tree.insert("", tk.END, values=(
            folder['local'],
            folder['remote'],
            mode_text,
            status,
            file_count,
            size_str
        ), tags=(status_tag,))
    
    def _load_folders(self):
        """Загрузка папок в таблицу"""
        self.tree.delete(*self.tree.get_children())
        
        for folder in self.sync_folders:
            self._insert_folder_row(folder)
    
    def add_folder(self):
        """Добавление новой папки через диалог"""
        dialog = FolderDialog(self, "Добавить папку для синхронизации")
        if dialog.result:
            # Проверка дубликатов
            for folder in self.sync_folders:
                if folder['local'] == dialog.result['local']:
                    messagebox.showwarning(
                        "Внимание", 
                        "Эта локальная папка уже добавлена в синхронизацию!"
                    )
                    return
            
            self.sync_folders.append(dialog.result)
            self._save_config()
            self._load_folders()
            logging.info(f"Добавлена папка для синхронизации: {dialog.result['local']}")
    
    def _edit_folder(self):
        """Редактирование выбранной папки"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        index = self.tree.index(item_id)
        folder = self.sync_folders[index]
        
        dialog = FolderDialog(self, "Редактировать папку", folder)
        if dialog.result:
            self.sync_folders[index] = dialog.result
            self._save_config()
            self._load_folders()
            logging.info(f"Обновлена папка синхронизации: {dialog.result['local']}")
    
    def _remove_folder(self):
        """Удаление выбранной папки"""
        selected = self.tree.selection()
        if not selected:
            return
        
        if messagebox.askyesno(
            "Подтверждение удаления",
            "Удалить папку из списка синхронизации?\n"
            "Сами файлы НЕ будут удалены с диска или из облака."
        ):
            item_id = selected[0]
            index = self.tree.index(item_id)
            folder = self.sync_folders.pop(index)
            
            self._save_config()
            self._load_folders()
            
            # Если синхронизация активна - перезапускаем для применения изменений
            if self.sync_engine.is_running():
                self.sync_engine.stop_sync()
                self.sync_engine.start_sync(self.sync_folders)
            
            logging.info(f"Удалена папка из синхронизации: {folder['local']}")
    
    def _open_folder(self):
        """Открытие локальной папки в проводнике"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        index = self.tree.index(item_id)
        folder_path = self.sync_folders[index]['local']
        
        if Path(folder_path).exists():
            import subprocess
            if os.name == 'nt':  # Windows
                os.startfile(folder_path)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', folder_path])
        else:
            messagebox.showerror("Ошибка", "Папка не найдена на диске")
    
    def _open_cloud(self):
        """Открытие папки в веб-интерфейсе Яндекс.Диска"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        index = self.tree.index(item_id)
        remote_path = self.sync_folders[index]['remote']
        
        import webbrowser
        webbrowser.open(f"https://disk.yandex.ru/client/disk{remote_path}")
    
    def _mark_for_delete(self):
        """Пометка файла на удаление только из облака"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        index = self.tree.index(item_id)
        folder = self.sync_folders[index]
        
        filepath = filedialog.askopenfilename(
            initialdir=folder['local'],
            title="Выберите файл для удаления из облака"
        )
        
        if filepath:
            marker_path = f"{filepath}.yd_delete"
            try:
                Path(marker_path).touch()
                messagebox.showinfo(
                    "Успешно",
                    "Файл помечен на удаление из облака.\n"
                    "При следующей синхронизации файл будет удалён только из Яндекс.Диска,\n"
                    "локальная копия сохранится."
                )
                logging.info(f"Файл помечен на удаление из облака: {filepath}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать маркер удаления:\n{str(e)}")
    
    def _empty_trash(self):
        """Очистка корзины синхронизации"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item_id = selected[0]
        index = self.tree.index(item_id)
        folder = self.sync_folders[index]
        
        trash_path = Path(folder['local']) / ".yd_trash"
        
        if not trash_path.exists() or not any(trash_path.iterdir()):
            messagebox.showinfo("Информация", "Корзина пуста")
            return
        
        if messagebox.askyesno(
            "Очистка корзины",
            f"Очистить корзину синхронизации?\n"
            f"Все файлы в папке {trash_path} будут безвозвратно удалены."
        ):
            try:
                import shutil
                shutil.rmtree(trash_path)
                trash_path.mkdir()
                messagebox.showinfo("Успешно", "Корзина очищена")
                logging.info(f"Корзина очищена: {trash_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось очистить корзину:\n{str(e)}")
    
    def _save_config(self):
        """Сохранение конфигурации"""
        self.config['sync_folders'] = self.sync_folders
        
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
    
    def _format_size(self, size_bytes: int) -> str:
        """Форматирование размера в человекочитаемый вид"""
        if size_bytes == 0:
            return "0 Б"
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ПБ"
    
    def get_sync_folders(self) -> list:
        """Получение списка синхронизируемых папок"""
        return self.sync_folders.copy()

class FolderDialog(tk.Toplevel):
    """Диалог добавления/редактирования папки синхронизации"""
    def __init__(self, parent, title, folder=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self.result = None
        self.folder = folder
        
        self._create_widgets()
        if folder:
            self._load_folder(folder)
        
        # Центрирование относительно родителя
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        self.wait_window(self)
    
    def _create_widgets(self):
        # Локальная папка
        ttkb.Label(self, text="Локальная папка:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(15, 5))
        
        path_frame = ttkb.Frame(self)
        path_frame.pack(fill=tk.X, padx=20)
        
        self.local_var = tk.StringVar()
        ttkb.Entry(path_frame, textvariable=self.local_var, width=60).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttkb.Button(
            path_frame,
            text="Обзор...",
            command=self._browse_local,
            bootstyle=SECONDARY,
            width=8
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Папка в облаке
        ttkb.Label(self, text="Папка в Яндекс.Диске:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(15, 5))
        
        self.remote_var = tk.StringVar(value="/Sync")
        ttkb.Entry(self, textvariable=self.remote_var, width=60).pack(padx=20, fill=tk.X)
        
        ttkb.Label(
            self,
            text="Путь должен начинаться с '/' (например: /Документы/Работа)",
            font=("Segoe UI", 8),
            foreground="#888"
        ).pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        # Режим синхронизации
        ttkb.Label(self, text="Режим синхронизации:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(10, 5))
        
        self.mode_var = tk.StringVar(value="one_way")
        
        mode_frame = ttkb.Frame(self)
        mode_frame.pack(fill=tk.X, padx=20)
        
        ttkb.Radiobutton(
            mode_frame,
            text="➡️ Односторонняя (локальные → облако)",
            variable=self.mode_var,
            value="one_way",
            bootstyle="success"
        ).pack(anchor=tk.W, pady=3)
        
        ttkb.Radiobutton(
            mode_frame,
            text="🔄 Двусторонняя (изменения в обе стороны)",
            variable=self.mode_var,
            value="two_way",
            bootstyle="info"
        ).pack(anchor=tk.W, pady=3)
        
        ttkb.Label(
            self,
            text="ℹ️ В двустороннем режиме возможны конфликты при одновременном редактировании.\n"
                 "Конфликтные версии сохраняются с пометкой '_conflict_'.",
            font=("Segoe UI", 8),
            foreground="#ff9900",
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=20, pady=(5, 15))
        
        # Кнопки
        btn_frame = ttkb.Frame(self)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        
        ttkb.Button(
            btn_frame,
            text="Сохранить",
            command=self._save,
            bootstyle=SUCCESS,
            width=12
        ).pack(side=tk.RIGHT, padx=5)
        
        ttkb.Button(
            btn_frame,
            text="Отмена",
            command=self.destroy,
            bootstyle=SECONDARY,
            width=12
        ).pack(side=tk.RIGHT, padx=5)
    
    def _browse_local(self):
        """Выбор локальной папки через диалог"""
        path = filedialog.askdirectory(title="Выберите папку для синхронизации")
        if path:
            self.local_var.set(path)
    
    def _load_folder(self, folder: dict):
        """Загрузка данных папки в форму"""
        self.local_var.set(folder.get('local', ''))
        self.remote_var.set(folder.get('remote', '/Sync'))
        self.mode_var.set(folder.get('mode', 'one_way'))
    
    def _save(self):
        """Сохранение результата диалога"""
        local_path = self.local_var.get().strip()
        remote_path = self.remote_var.get().strip()
        
        # Валидация
        if not local_path:
            messagebox.showerror("Ошибка", "Укажите локальную папку")
            return
        
        if not Path(local_path).exists():
            messagebox.showerror("Ошибка", "Локальная папка не существует")
            return
        
        if not remote_path.startswith('/'):
            messagebox.showerror("Ошибка", "Путь в облаке должен начинаться с '/'")
            return
        
        self.result = {
            'local': local_path,
            'remote': remote_path.rstrip('/'),
            'mode': self.mode_var.get()
        }
        
        self.destroy()