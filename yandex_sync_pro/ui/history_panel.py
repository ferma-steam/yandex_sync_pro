import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttkb
from datetime import datetime
import csv

class HistoryPanel(ttk.Frame):
    def __init__(self, parent, metadata_manager):
        super().__init__(parent)
        self.metadata = metadata_manager
        self._create_widgets()
        self._load_history()
    
    def _create_widgets(self):
        # Панель фильтров
        filter_frame = ttkb.LabelFrame(self, text="Фильтры", padding=10)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Тип операции
        ttkb.Label(filter_frame, text="Тип:").grid(row=0, column=0, padx=5, pady=5)
        self.type_var = tk.StringVar(value="all")
        type_combo = ttkb.Combobox(filter_frame, textvariable=self.type_var, width=15, state="readonly")
        type_combo['values'] = ["all", "upload", "download", "delete", "conflict"]
        type_combo.grid(row=0, column=1, padx=5, pady=5)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        # Дата
        ttkb.Label(filter_frame, text="Период:").grid(row=0, column=2, padx=5, pady=5)
        self.date_var = tk.StringVar(value="all")
        date_combo = ttkb.Combobox(filter_frame, textvariable=self.date_var, width=15, state="readonly")
        date_combo['values'] = ["all", "today", "week", "month"]
        date_combo.grid(row=0, column=3, padx=5, pady=5)
        date_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        
        # Поиск
        ttkb.Label(filter_frame, text="Поиск:").grid(row=0, column=4, padx=5, pady=5)
        self.search_var = tk.StringVar()
        search_entry = ttkb.Entry(filter_frame, textvariable=self.search_var, width=25)
        search_entry.grid(row=0, column=5, padx=5, pady=5)
        search_entry.bind("<KeyRelease>", lambda e: self._apply_filters())
        
        ttkb.Button(filter_frame, text="Очистить", command=self._clear_filters, 
                   bootstyle="secondary").grid(row=0, column=6, padx=10, pady=5)
        
        # Таблица истории
        table_frame = ttkb.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ("timestamp", "operation", "path", "status", "size")
        self.tree = ttkb.Treeview(table_frame, columns=columns, show="headings", height=15)
        
        # Настройка колонок
        self.tree.heading("timestamp", text="Время")
        self.tree.heading("operation", text="Операция")
        self.tree.heading("path", text="Путь")
        self.tree.heading("status", text="Статус")
        self.tree.heading("size", text="Размер")
        
        self.tree.column("timestamp", width=150, anchor="center")
        self.tree.column("operation", width=100, anchor="center")
        self.tree.column("path", width=400)
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("size", width=80, anchor="center")
        
        # Стилизация статусов
        self.tree.tag_configure("success", foreground="#4CAF50")
        self.tree.tag_configure("error", foreground="#F44336")
        self.tree.tag_configure("warning", foreground="#FF9800")
        
        # Скроллбары
        vsb = ttkb.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttkb.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Контекстное меню
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Экспортировать выделенное в CSV", 
                                    command=self._export_selection)
        self.context_menu.add_command(label="Экспортировать всю историю в CSV", 
                                    command=self._export_all)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Очистить историю", 
                                    command=self._clear_history)
    
    def _load_history(self, filters=None):
        """Загрузка истории с фильтрацией"""
        # Очистка таблицы
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Получение данных
        history = self.metadata.get_operation_history(filters)
        
        # Заполнение таблицы
        for entry in history:
            tags = []
            if entry['status'] == 'success':
                tags.append('success')
            elif entry['status'] == 'error':
                tags.append('error')
            elif entry['status'] == 'conflict':
                tags.append('warning')
            
            self.tree.insert("", "end", values=(
                entry['timestamp'],
                self._get_operation_icon(entry['operation']),
                entry['path'],
                entry['status'].upper(),
                self._format_size(entry['size'])
            ), tags=tags)
    
    def _apply_filters(self):
        """Применение фильтров"""
        filters = {
            'operation': None if self.type_var.get() == 'all' else self.type_var.get(),
            'period': self.date_var.get(),
            'search': self.search_var.get().strip() or None
        }
        self._load_history(filters)
    
    def _clear_filters(self):
        """Очистка фильтров"""
        self.type_var.set("all")
        self.date_var.set("all")
        self.search_var.set("")
        self._load_history()
    
    def _show_context_menu(self, event):
        """Показ контекстного меню"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def _export_selection(self):
        """Экспорт выделенных записей в CSV"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Нет выделенных записей для экспорта")
            return
        
        filename = f"ydsync_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = tk.filedialog.asksaveasfilename(
            initialfile=filename,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["Время", "Операция", "Путь", "Статус", "Размер"])
                
                for item_id in selected:
                    values = self.tree.item(item_id)['values']
                    writer.writerow(values)
            
            messagebox.showinfo("Успешно", f"Экспортировано {len(selected)} записей в:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать историю:\n{str(e)}")
    
    def _export_all(self):
        """Экспорт всей истории в CSV"""
        filename = f"ydsync_full_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = tk.filedialog.asksaveasfilename(
            initialfile=filename,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            history = self.metadata.get_operation_history()
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["Время", "Операция", "Путь", "Статус", "Размер"])
                
                for entry in history:
                    writer.writerow([
                        entry['timestamp'],
                        entry['operation'],
                        entry['path'],
                        entry['status'],
                        entry['size']
                    ])
            
            messagebox.showinfo("Успешно", f"Экспортировано {len(history)} записей в:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать историю:\n{str(e)}")
    
    def _clear_history(self):
        """Очистка истории"""
        if messagebox.askyesno("Подтверждение", 
                             "Очистить всю историю операций?\nЭто действие нельзя отменить!"):
            self.metadata.clear_operation_history()
            self._load_history()
            messagebox.showinfo("Успешно", "История операций очищена")
    
    @staticmethod
    def _get_operation_icon(operation):
        """Иконки для операций"""
        icons = {
            'upload': '📤',
            'download': '📥',
            'delete': '🗑️',
            'conflict': '⚠️',
            'sync': '🔄'
        }
        return f"{icons.get(operation, '⚙️')} {operation}"
    
    @staticmethod
    def _format_size(size_bytes):
        """Форматирование размера"""
        if not size_bytes or size_bytes == 0:
            return "-"
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ТБ"
    
    def refresh(self):
        """Обновление истории"""
        self._apply_filters()