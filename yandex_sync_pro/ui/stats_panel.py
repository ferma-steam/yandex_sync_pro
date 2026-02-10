import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import numpy as np

class StatsPanel(ttk.Frame):
    def __init__(self, parent, metadata_manager):
        super().__init__(parent)
        self.metadata = metadata_manager
        self._create_widgets()
        self._load_data()
    
    def _create_widgets(self):
        # Верхняя панель с карточками статистики
        cards_frame = ttk.Frame(self)
        cards_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.cards = {}
        metrics = [
            ("Всего файлов", "files_total"),
            ("Синхронизировано сегодня", "files_today"),
            ("Общий трафик", "total_traffic"),
            ("Последняя синхронизация", "last_sync")
        ]
        
        for i, (label, key) in enumerate(metrics):
            card = ttk.Frame(cards_frame, relief="ridge", borderwidth=1)
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            cards_frame.columnconfigure(i, weight=1)
            
            ttk.Label(card, text=label, font=("Segoe UI", 9, "bold")).pack(pady=(5, 0))
            value_label = ttk.Label(card, text="--", font=("Segoe UI", 14, "bold"), foreground="#4CAF50")
            value_label.pack(pady=5)
            self.cards[key] = value_label
        
        # Графики
        charts_frame = ttk.Frame(self)
        charts_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # График трафика за неделю
        self.traffic_fig = Figure(figsize=(5, 3), dpi=100)
        self.traffic_ax = self.traffic_fig.add_subplot(111)
        self.traffic_canvas = FigureCanvasTkAgg(self.traffic_fig, charts_frame)
        self.traffic_canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # График количества файлов
        self.files_fig = Figure(figsize=(5, 3), dpi=100)
        self.files_ax = self.files_fig.add_subplot(111)
        self.files_canvas = FigureCanvasTkAgg(self.files_fig, charts_frame)
        self.files_canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
    
    def _load_data(self):
        """Загрузка данных для статистики"""
        # Карточки
        stats = self.metadata.get_sync_statistics()
        self.cards["files_total"].config(text=f"{stats['total_files']:,}")
        self.cards["files_today"].config(text=f"{stats['today_files']:,}")
        self.cards["total_traffic"].config(text=self._format_bytes(stats['total_bytes']))
        self.cards["last_sync"].config(text=stats['last_sync'] or "никогда")
        
        # Графики
        self._plot_traffic_chart()
        self._plot_files_chart()
    
    def _plot_traffic_chart(self):
        """График сетевого трафика за неделю"""
        traffic_data = self.metadata.get_traffic_history(days=7)
        
        dates = [d['date'] for d in traffic_data]
        upload = [d['upload'] for d in traffic_data]
        download = [d['download'] for d in traffic_data]
        
        self.traffic_ax.clear()
        x = np.arange(len(dates))
        width = 0.35
        
        self.traffic_ax.bar(x - width/2, upload, width, label='Загрузка', color='#4CAF50')
        self.traffic_ax.bar(x + width/2, download, width, label='Скачивание', color='#2196F3')
        
        self.traffic_ax.set_ylabel('Трафик (МБ)')
        self.traffic_ax.set_title('Сетевой трафик за неделю')
        self.traffic_ax.set_xticks(x)
        self.traffic_ax.set_xticklabels([d[5:] for d in dates], rotation=45)  # Только месяц-день
        self.traffic_ax.legend()
        self.traffic_ax.grid(axis='y', alpha=0.3)
        
        self.traffic_fig.tight_layout()
        self.traffic_canvas.draw()
    
    def _plot_files_chart(self):
        """График количества синхронизированных файлов"""
        files_data = self.metadata.get_files_history(days=30)
        
        dates = [d['date'] for d in files_data]
        counts = [d['count'] for d in files_data]
        
        self.files_ax.clear()
        self.files_ax.plot(dates, counts, marker='o', linewidth=2, color='#FF9800')
        self.files_ax.fill_between(range(len(counts)), counts, alpha=0.3, color='#FF9800')
        
        self.files_ax.set_ylabel('Файлов')
        self.files_ax.set_title('Синхронизированные файлы (30 дней)')
        self.files_ax.set_xticks(range(0, len(dates), max(1, len(dates)//10)))
        self.files_ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), max(1, len(dates)//10))], rotation=45)
        self.files_ax.grid(alpha=0.3)
        
        self.files_fig.tight_layout()
        self.files_canvas.draw()
    
    @staticmethod
    def _format_bytes(bytes_value):
        """Форматирование байтов в человекочитаемый вид"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} ПБ"
    
    def refresh(self):
        """Обновление статистики"""
        self._load_data()