import customtkinter as ctk
import os
import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import filedialog
from interfaces import IView, IDataService
from styles import *

class DashboardViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._setup_ui()

    def get_frame(self) -> ctk.CTkFrame: return self

    def _setup_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 30))
        ctk.CTkLabel(header_frame, text="Inicio", font=FONT_TITLE, text_color=COLOR_TEXT_DARK).pack(side="left")
        
        # Stats Cards
        self.stats_container = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_container.pack(fill="x", pady=(0, 30))
        
        datasets = self._data_service.get_all_datasets()
        stats = [
            ("Total Datasets", str(len(datasets)), COLOR_PRIMARY),
            ("Validaciones", "75", COLOR_SUCCESS),
            ("Inconsistencias", "350", COLOR_WARNING),
            ("Críticas", "25", COLOR_ERROR)
        ]
        
        for i, (title, value, color) in enumerate(stats):
            card = ctk.CTkFrame(self.stats_container, height=140, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
            card.grid(row=0, column=i, padx=10, sticky="nsew")
            card.grid_propagate(False)
            ctk.CTkFrame(card, height=4, fg_color=color, corner_radius=0).pack(fill="x", side="top")
            ctk.CTkLabel(card, text=title, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).pack(pady=(20, 5))
            ctk.CTkLabel(card, text=value, font=(FONT_FAMILY, 36, "bold"), text_color=COLOR_TEXT_DARK).pack()
        
        self.stats_container.grid_columnconfigure((0,1,2,3), weight=1)

class DatasetViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._setup_ui()

    def get_frame(self) -> ctk.CTkFrame: return self

    def _setup_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 25))
        ctk.CTkLabel(header_frame, text="Gestión de Datasets", font=FONT_TITLE, text_color=COLOR_TEXT_DARK).pack(side="left")
        
        # Upload Area
        self.upload_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.upload_card.pack(fill="x", pady=(0, 25))
        
        content = ctk.CTkFrame(self.upload_card, fg_color="transparent")
        content.pack(pady=40)
        ctk.CTkLabel(content, text="Seleccione un archivo CSV o JSON para analizar", font=FONT_HEADING).pack()
        
        self.btn_row = ctk.CTkFrame(content, fg_color="transparent")
        self.btn_row.pack(pady=20)
        ctk.CTkButton(self.btn_row, text="Buscar Archivo", command=self.select_file, fg_color=COLOR_PRIMARY).pack(side="left", padx=10)
        self.upload_btn = ctk.CTkButton(self.btn_row, text="Cargar Dataset", command=self.upload_file, fg_color=COLOR_SUCCESS, state="disabled")
        self.upload_btn.pack(side="left", padx=10)

        # Datasets Table
        ctk.CTkLabel(self, text="Datasets Cargados", font=FONT_SUBTITLE, text_color=COLOR_TEXT_DARK).pack(anchor="w", pady=(0, 15))
        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        self.refresh_table()

    def refresh_table(self):
        for widget in self.table_card.winfo_children(): widget.destroy()
        headers = ["ID", "Nombre del Archivo", "Tipo", "Registros", "Fecha", "Estado"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_card, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=20, pady=15)
            self.table_card.grid_columnconfigure(i, weight=1)
        
        for r_idx, ds in enumerate(self._data_service.get_all_datasets(), start=1):
            ctk.CTkLabel(self.table_card, text=ds["id"]).grid(row=r_idx, column=0, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds["name"], font=FONT_LABEL_BOLD).grid(row=r_idx, column=1, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds["type"]).grid(row=r_idx, column=2, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=f"{ds['records']:,}").grid(row=r_idx, column=3, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds["date"]).grid(row=r_idx, column=4, sticky="w", padx=20, pady=10)
            badge = ctk.CTkFrame(self.table_card, fg_color=COLOR_SUCCESS, corner_radius=12)
            badge.grid(row=r_idx, column=5, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(badge, text=ds["status"], font=FONT_SMALL, text_color=COLOR_WHITE).pack(padx=8, pady=1)

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("Archivos de Datos", "*.csv *.json")])
        if path:
            self.selected_path = path
            self.upload_btn.configure(state="normal")

    def upload_file(self):
        name = os.path.basename(self.selected_path)
        ext = name.split(".")[-1]
        self._data_service.add_dataset(name, ext, 1000)
        self.refresh_table()
        self.upload_btn.configure(state="disabled")

class ValidationViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        ctk.CTkLabel(self, text="Ejecución de Validación", font=FONT_TITLE).pack(anchor="w", pady=(0, 25))
        
        self.select_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.select_card.pack(fill="x", pady=(0, 25))
        
        ds_names = [ds["name"] for ds in self._data_service.get_all_datasets()]
        self.selector = ctk.CTkComboBox(self.select_card, values=ds_names, width=500, height=40)
        self.selector.pack(anchor="w", padx=25, pady=25)
        ctk.CTkButton(self.select_card, text="Iniciar Validación", fg_color=COLOR_PRIMARY, height=50).pack(fill="x", padx=25, pady=(0, 25))

    def get_frame(self) -> ctk.CTkFrame: return self

class FindingsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text="Hallazgos Detectados", font=FONT_TITLE).pack(anchor="w", pady=(0, 25))
        
        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        
        headers = ["ID", "Regla", "Campo", "Valor", "Severidad"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_card, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=20, pady=15)
            self.table_card.grid_columnconfigure(i, weight=1)

    def get_frame(self) -> ctk.CTkFrame: return self

class RecommendationsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text="Recomendaciones del Sistema", font=FONT_TITLE).pack(anchor="w", pady=(0, 25))
        
        self.card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.card.pack(fill="both", expand=True)
        
        recs = [("Formato Fecha", "Asegurar formato DD-MM-YYYY.", "Limpieza"), ("Rango Edad", "Corregir valores > 120.", "Corrección")]
        for r_idx, (regla, desc, tipo) in enumerate(recs):
            ctk.CTkLabel(self.card, text=regla, font=FONT_LABEL_BOLD).grid(row=r_idx, column=0, padx=20, pady=15)
            ctk.CTkLabel(self.card, text=desc).grid(row=r_idx, column=1, padx=20, pady=15)
            ctk.CTkLabel(self.card, text=tipo).grid(row=r_idx, column=2, padx=20, pady=15)

    def get_frame(self) -> ctk.CTkFrame: return self

class StatsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text="Estadísticas", font=FONT_TITLE).pack(anchor="w", pady=(0, 25))
        
        self.charts_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.charts_frame.pack(fill="both", expand=True)
        
        self.create_chart(self.charts_frame, "Severidad", 0, 0)
        self.create_chart(self.charts_frame, "Detección", 0, 1)

    def get_frame(self) -> ctk.CTkFrame: return self

    def create_chart(self, parent, title, r, c):
        card = ctk.CTkFrame(parent, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(card, text=title, font=FONT_LABEL_BOLD).pack(pady=10)
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar(['Crítica', 'Media', 'Baja'], [120, 180, 50], color=[ACCENT_CRITICAL, ACCENT_MEDIUM, ACCENT_LOW])
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        parent.grid_columnconfigure((0, 1), weight=1)
