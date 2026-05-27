import customtkinter as ctk
from tkinter import filedialog

from core.interfaces import IDataService, IView
from ui.styles import *


def _normalize_column_name(name: str) -> str:
    return "".join(ch for ch in (name or "").strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")


class DashboardViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._setup_ui()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def _setup_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 30))
        ctk.CTkLabel(header_frame, text="Inicio", font=FONT_TITLE, text_color=COLOR_TEXT_DARK).pack(side="left")
        ctk.CTkButton(header_frame, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        self.stats_container = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_container.pack(fill="x", pady=(0, 30))
        self._stat_value_labels = {}
        stats = [
            ("Total Datasets", "datasets", COLOR_PRIMARY),
            ("Validaciones", "validations", COLOR_SUCCESS),
            ("Inconsistencias", "inconsistencies", COLOR_WARNING),
            ("Cr\u00edticas", "critical", COLOR_ERROR),
        ]
        for i, (title, key, color) in enumerate(stats):
            card = ctk.CTkFrame(self.stats_container, height=140, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
            card.grid(row=0, column=i, padx=10, sticky="nsew")
            card.grid_propagate(False)
            ctk.CTkFrame(card, height=4, fg_color=color, corner_radius=0).pack(fill="x", side="top")
            ctk.CTkLabel(card, text=title, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).pack(pady=(20, 5))
            value_label = ctk.CTkLabel(card, text="0", font=(FONT_FAMILY, 36, "bold"), text_color=COLOR_TEXT_DARK)
            value_label.pack()
            self._stat_value_labels[key] = value_label
        self.stats_container.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.refresh()

    def refresh(self):
        stats = self._data_service.get_dashboard_stats()
        for key, label in self._stat_value_labels.items():
            label.configure(text=str(stats.get(key, 0)))


class DatasetSchemaDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        columns: list[str],
        suggested_required: list[str] | None = None,
        record_count: int | None = None,
        folio_count: int | None = None,
        file_name: str | None = None,
    ):
        super().__init__(master)
        self.title("Configuración de estructura")
        self.geometry("1100x650")
        self.resizable(True, True)
        self._result = None
        self._columns = list(columns)

        suggested_required = suggested_required or []
        normalized_to_original = {_normalize_column_name(c): c for c in self._columns}
        self._suggested_present: set[str] = set()
        for s in suggested_required:
            key = _normalize_column_name(s)
            if key in normalized_to_original:
                self._suggested_present.add(normalized_to_original[key])
        self._suggested_missing = [s for s in suggested_required if _normalize_column_name(s) not in normalized_to_original]

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(top, text="Configuración de estructura del archivo", font=FONT_HEADING).pack(anchor="w")

        cols_count = len(self._columns)
        records_text = f"{record_count:,}" if record_count is not None else "N/A"
        folios_text = f"{folio_count:,}" if folio_count is not None else "N/A"
        file_text = file_name or "Archivo seleccionado"
        ctk.CTkLabel(top, text=file_text, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(
            top,
            text=f"Columnas: {cols_count} | Registros (sin encabezado): {records_text} | Folios: {folios_text}",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=(0, 10))

        self._search_entry = ctk.CTkEntry(controls, placeholder_text="Buscar columna...", width=360, height=38)
        self._search_entry.pack(side="left")
        self._search_entry.bind("<KeyRelease>", lambda _e: self._apply_filter())

        actions = ctk.CTkFrame(controls, fg_color="transparent")
        actions.pack(side="right")
        ctk.CTkButton(actions, text="Solo sugeridos", width=140, fg_color=COLOR_SECONDARY, command=self._filter_suggested).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(actions, text="Marcar sugeridos", width=160, fg_color=COLOR_PRIMARY, command=self._mark_suggested).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(actions, text="Limpiar", width=120, fg_color=COLOR_WARNING, command=self._clear_all).pack(side="left")

        card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        if self._suggested_missing:
            ctk.CTkLabel(
                card,
                text="Sugeridos obligatorios faltantes en el archivo: " + ", ".join(self._suggested_missing),
                font=FONT_SMALL,
                text_color=COLOR_WARNING,
                wraplength=1040,
                justify="left",
            ).pack(anchor="w", padx=18, pady=(16, 8))
        else:
            ctk.CTkLabel(
                card,
                text="Selecciona qué columnas serán obligatorias y cuáles representan fecha u hora.",
                font=FONT_SMALL,
                text_color=COLOR_TEXT_MUTED,
            ).pack(anchor="w", padx=18, pady=(16, 8))

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)
        for col, title in enumerate(("Columna", "Obligatorio", "Fecha", "Hora")):
            sticky = "w" if col == 0 else ""
            ctk.CTkLabel(header, text=title, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(
                row=0, column=col, sticky=sticky, padx=(0, 12) if col < 3 else (0, 0)
            )

        self._required_checks: dict[str, ctk.CTkCheckBox] = {}
        self._date_checks: dict[str, ctk.CTkCheckBox] = {}
        self._time_checks: dict[str, ctk.CTkCheckBox] = {}
        self._row_frames: dict[str, ctk.CTkFrame] = {}

        table = ctk.CTkScrollableFrame(card, fg_color="transparent")
        table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for idx, c in enumerate(self._columns):
            row = ctk.CTkFrame(table, fg_color="transparent")
            row.grid(row=idx, column=0, sticky="ew", padx=6, pady=3)
            row.grid_columnconfigure(0, weight=1)
            self._row_frames[c] = row

            label_text = f"{c} (sugerido)" if c in self._suggested_present else c
            ctk.CTkLabel(row, text=label_text, font=FONT_LABEL, text_color=COLOR_TEXT_DARK).grid(row=0, column=0, sticky="w")

            req = ctk.CTkCheckBox(row, text="", onvalue=True, offvalue=False, width=22)
            req.grid(row=0, column=1, padx=(0, 10))
            dt = ctk.CTkCheckBox(row, text="", onvalue=True, offvalue=False, width=22)
            dt.grid(row=0, column=2, padx=(0, 10))
            tm = ctk.CTkCheckBox(row, text="", onvalue=True, offvalue=False, width=22)
            tm.grid(row=0, column=3)

            self._required_checks[c] = req
            self._date_checks[c] = dt
            self._time_checks[c] = tm

            norm = _normalize_column_name(c)
            if c in self._suggested_present:
                req.select()
            if "fecha" in norm:
                dt.select()
            if "hora" in norm:
                tm.select()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))

        presets = ctk.CTkFrame(btn_row, fg_color="transparent")
        presets.pack(side="left")
        ctk.CTkButton(presets, text="Todo obligatorio", width=160, fg_color=COLOR_SECONDARY, command=lambda: self._set_all("required", True)).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(presets, text="Todo fecha", width=140, fg_color=COLOR_SECONDARY, command=lambda: self._set_all("date", True)).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkButton(presets, text="Todo hora", width=140, fg_color=COLOR_SECONDARY, command=lambda: self._set_all("time", True)).pack(
            side="left"
        )

        ctk.CTkButton(btn_row, text="Cancelar", fg_color=COLOR_ERROR, command=self._cancel).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_row, text="Guardar", fg_color=COLOR_SUCCESS, command=self._save).pack(side="right")

        self.grab_set()
        self.focus_set()

    def _set_all(self, kind: str, value: bool):
        lookup = {
            "required": self._required_checks,
            "date": self._date_checks,
            "time": self._time_checks,
        }.get(kind)
        if not lookup:
            return
        for cb in lookup.values():
            if value:
                cb.select()
            else:
                cb.deselect()

    def _clear_all(self):
        self._set_all("required", False)
        self._set_all("date", False)
        self._set_all("time", False)
        self._apply_filter()

    def _mark_suggested(self):
        for c in self._suggested_present:
            self._required_checks[c].select()
        self._apply_filter()

    def _filter_suggested(self):
        self._search_entry.delete(0, "end")
        for c, row in self._row_frames.items():
            if c in self._suggested_present:
                row.grid()
            else:
                row.grid_remove()

    def _apply_filter(self):
        q = (self._search_entry.get() or "").strip().lower()
        if not q:
            for row in self._row_frames.values():
                row.grid()
            return
        qn = _normalize_column_name(q)
        for c, row in self._row_frames.items():
            cn = _normalize_column_name(c)
            if q in c.lower() or qn in cn:
                row.grid()
            else:
                row.grid_remove()

    def _save(self):
        required_columns = [c for c, cb in self._required_checks.items() if cb.get()]
        date_columns = [c for c, cb in self._date_checks.items() if cb.get()]
        time_columns = [c for c, cb in self._time_checks.items() if cb.get()]
        self._result = {"required_columns": required_columns, "date_columns": date_columns, "time_columns": time_columns}
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get_result(self):
        return self._result


class DatasetViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._setup_ui()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def _setup_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 25))
        ctk.CTkLabel(header_frame, text="Gestión de Datasets", font=FONT_TITLE, text_color=COLOR_TEXT_DARK).pack(side="left")

        self.upload_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.upload_card.pack(fill="x", pady=(0, 25))

        content = ctk.CTkFrame(self.upload_card, fg_color="transparent")
        content.pack(pady=40)
        ctk.CTkLabel(content, text="Seleccione un archivo CSV para analizar", font=FONT_HEADING).pack()

        self.btn_row = ctk.CTkFrame(content, fg_color="transparent")
        self.btn_row.pack(pady=20)
        ctk.CTkButton(self.btn_row, text="Buscar Archivo", command=self.select_file, fg_color=COLOR_PRIMARY).pack(side="left", padx=10)
        self.upload_btn = ctk.CTkButton(self.btn_row, text="Cargar Dataset", command=self.upload_file, fg_color=COLOR_SUCCESS, state="disabled")
        self.upload_btn.pack(side="left", padx=10)

        ctk.CTkLabel(self, text="Datasets Cargados", font=FONT_SUBTITLE, text_color=COLOR_TEXT_DARK).pack(anchor="w", pady=(0, 15))
        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        self.refresh_table()

    def refresh_table(self):
        for widget in self.table_card.winfo_children():
            widget.destroy()
        headers = ["ID", "Nombre del Archivo", "Tipo", "Registros", "Folios", "Fecha", "Hora", "Usuario", "Estado"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_card, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=20, pady=15)
            self.table_card.grid_columnconfigure(i, weight=1)

        for r_idx, ds in enumerate(self._data_service.get_all_datasets(), start=1):
            ctk.CTkLabel(self.table_card, text=str(ds["id"])[:8]).grid(row=r_idx, column=0, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds["name"], font=FONT_LABEL_BOLD).grid(row=r_idx, column=1, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds["type"]).grid(row=r_idx, column=2, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=f"{ds['records']:,}").grid(row=r_idx, column=3, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=f"{int(ds.get('folios', ds['records'])):,}").grid(row=r_idx, column=4, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds.get("date", "Hoy")).grid(row=r_idx, column=5, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds.get("time", "")).grid(row=r_idx, column=6, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.table_card, text=ds.get("user_email", "")).grid(row=r_idx, column=7, sticky="w", padx=20, pady=10)
            badge = ctk.CTkFrame(self.table_card, fg_color=COLOR_SUCCESS, corner_radius=12)
            badge.grid(row=r_idx, column=8, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(badge, text=ds.get("status", "OK"), font=FONT_SMALL, text_color=COLOR_ON_COLOR).pack(padx=8, pady=1)

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("Archivos CSV", "*.csv")])
        if path:
            self.selected_path = path
            self.upload_btn.configure(state="normal")

    def upload_file(self):
        try:
            import tkinter.messagebox as messagebox
            import pandas as pd

            df = pd.read_csv(self.selected_path)
            columns = [str(c) for c in df.columns]
            record_count = int(len(df))
            normalized_to_original = {_normalize_column_name(c): c for c in columns}
            folio_col = None
            for key in ("folio_reporte", "folioreporte", "folio"):
                if key in normalized_to_original:
                    folio_col = normalized_to_original[key]
                    break
            if not folio_col:
                for norm, original in normalized_to_original.items():
                    if "folio" in norm and "reporte" in norm:
                        folio_col = original
                        break
            if folio_col and folio_col in df.columns:
                s = df[folio_col].astype(str).str.strip()
                folio_count = int(s[s != ""].nunique())
            else:
                folio_count = record_count

            suggested_required = []
            try:
                suggested_required = self._data_service.get_suggested_required_columns()
            except Exception:
                suggested_required = []

            dialog = DatasetSchemaDialog(
                self,
                columns,
                suggested_required=suggested_required,
                record_count=record_count,
                folio_count=folio_count,
                file_name=str(self.selected_path).split("\\")[-1],
            )
            dialog.wait_window()
            schema = dialog.get_result()
            if not schema:
                return

            dataset = self._data_service.import_dataset(self.selected_path, schema)
            messagebox.showinfo(
                "Éxito",
                f"Dataset cargado correctamente.\nSe leyeron {dataset['records']} registros y {int(dataset.get('folios', dataset['records']))} folios del archivo:\n{dataset['name']}",
            )
        except Exception as e:
            import tkinter.messagebox as messagebox

            messagebox.showerror("Error", f"No se pudo cargar el dataset:\n{str(e)}")
            return

        self.refresh_table()
        self.upload_btn.configure(state="disabled")


class ValidationViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._dataset_label_to_id = {}
        self._last_run_id = None
        self._setup_ui()

    def _setup_ui(self):
        ctk.CTkLabel(self, text="Ejecución de Validación", font=FONT_TITLE, text_color=COLOR_TEXT_DARK).pack(anchor="w", pady=(0, 18))

        self.main_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.main_card.pack(fill="both", expand=True)

        top_row = ctk.CTkFrame(self.main_card, fg_color="transparent")
        top_row.pack(fill="x", padx=25, pady=(25, 10))
        ctk.CTkLabel(top_row, text="Seleccionar Dataset", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(side="left")
        ctk.CTkButton(top_row, text="🔄 Actualizar", width=140, fg_color=COLOR_PRIMARY, command=self.refresh_datasets).pack(side="right")

        self.selector = ctk.CTkComboBox(
            self.main_card,
            values=["No hay datasets disponibles"],
            width=700,
            height=40,
            state="readonly",
            command=self.on_dataset_change,
        )
        self.selector.pack(anchor="w", padx=25, pady=(0, 15))

        self.btn_validate = ctk.CTkButton(
            self.main_card, text="Ejecutar Validación", fg_color=COLOR_PRIMARY, height=44, command=self.run_validation
        )
        self.btn_validate.pack(fill="x", padx=25, pady=(0, 18))

        cards_row = ctk.CTkFrame(self.main_card, fg_color="transparent")
        cards_row.pack(fill="x", padx=25, pady=(0, 18))
        cards_row.grid_columnconfigure((0, 1), weight=1)

        self.ds_info_card = ctk.CTkFrame(cards_row, fg_color=COLOR_BG_LIGHT, corner_radius=CARD_RADIUS)
        self.ds_info_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(self.ds_info_card, text="Información del Dataset Seleccionado", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=18, pady=(16, 10)
        )
        self.ds_name_value = ctk.CTkLabel(self.ds_info_card, text="Nombre: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.ds_name_value.pack(anchor="w", padx=18, pady=4)
        self.ds_id_value = ctk.CTkLabel(self.ds_info_card, text="Dataset ID: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.ds_id_value.pack(anchor="w", padx=18, pady=4)
        self.ds_date_value = ctk.CTkLabel(self.ds_info_card, text="Fecha de carga: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.ds_date_value.pack(anchor="w", padx=18, pady=(4, 16))

        self.proc_card = ctk.CTkFrame(cards_row, fg_color=COLOR_BG_LIGHT, corner_radius=CARD_RADIUS)
        self.proc_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(self.proc_card, text="Estado del Proceso de Validación", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=18, pady=(16, 10)
        )
        self.proc_status_value = ctk.CTkLabel(self.proc_card, text="Estado: Pendiente", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.proc_status_value.pack(anchor="w", padx=18, pady=4)
        self.proc_start_value = ctk.CTkLabel(self.proc_card, text="Fecha de inicio: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.proc_start_value.pack(anchor="w", padx=18, pady=4)
        self.proc_end_value = ctk.CTkLabel(self.proc_card, text="Fecha de finalización: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.proc_end_value.pack(anchor="w", padx=18, pady=4)
        self.proc_total_value = ctk.CTkLabel(
            self.proc_card, text="Total de inconsistencias detectadas: N/A", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED
        )
        self.proc_total_value.pack(anchor="w", padx=18, pady=(4, 16))

        self.btn_view_findings = ctk.CTkButton(
            self.main_card, text="Ver Hallazgos", fg_color=COLOR_SUCCESS, height=44, state="disabled", command=self.open_findings_dialog
        )
        self.btn_view_findings.pack(fill="x", padx=25, pady=(0, 18))

        self.advanced_toggle_btn = ctk.CTkButton(
            self.main_card, text="Opciones avanzadas ▼", fg_color=COLOR_SECONDARY, height=40, command=self.toggle_advanced
        )
        self.advanced_toggle_btn.pack(fill="x", padx=25, pady=(0, 18))

        self.advanced_open = False
        self.advanced_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")

        ctk.CTkLabel(self.advanced_frame, text="Reglas de validación (INCONSISTENCIAS.pdf)", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", pady=(0, 5)
        )
        self.rules_frame = ctk.CTkScrollableFrame(self.advanced_frame, height=160, fg_color="transparent")
        self.rules_frame.pack(fill="x", pady=(0, 15))
        self.checkboxes = {}
        self._render_rules()

        ctk.CTkLabel(self.advanced_frame, text="Mapa de columnas (según tu CSV)", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", pady=(0, 5)
        )
        self.mapping_frame = ctk.CTkFrame(self.advanced_frame, fg_color="transparent")
        self.mapping_frame.pack(fill="x", pady=(0, 10))
        self._mapping_widgets = {}
        self._render_mapping([])

        self.refresh_datasets()

    def refresh_datasets(self):
        datasets = self._data_service.get_all_datasets()
        self._dataset_label_to_id = {}
        values = []
        for ds in datasets:
            label = f"{str(ds['id'])[:8]} - {ds['name']}"
            self._dataset_label_to_id[label] = ds["id"]
            values.append(label)
        if not values:
            values = ["No hay datasets disponibles"]
        self.selector.configure(values=values)
        self.selector.set(values[0])
        self.on_dataset_change(values[0])

    def _render_rules(self):
        for w in self.rules_frame.winfo_children():
            w.destroy()
        self.checkboxes = {}
        rules = self._data_service.get_rules()
        for r in rules:
            cb = ctk.CTkCheckBox(self.rules_frame, text=f"{r['name']} — {r['description']}", onvalue=True, offvalue=False)
            cb.pack(anchor="w", pady=4)
            if bool(r.get("active", True)):
                cb.select()
            self.checkboxes[r["id"]] = cb

    def _render_mapping(self, columns: list[str]):
        for w in self.mapping_frame.winfo_children():
            w.destroy()
        self._mapping_widgets = {}
        options = ["(sin seleccionar)"] + list(columns)

        fields = [
            ("conductor_col", "Columna de conductor"),
            ("carta_porte_col", "Columna de Carta Porte"),
            ("cliente_col", "Columna de cliente"),
            ("fecha_col", "Columna de fecha (para duplicidad)"),
            ("direccion_col", "Columna de dirección"),
            ("empleado_col", "Columna de número de empleado"),
            ("placas_col", "Columna de placas"),
            ("peso_col", "Columna de peso"),
            ("fecha_salida_col", "Columna fecha salida"),
            ("fecha_llegada_col", "Columna fecha llegada"),
        ]

        for i, (key, label) in enumerate(fields):
            row = ctk.CTkFrame(self.mapping_frame, fg_color="transparent")
            row.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 12) if i % 2 == 0 else (12, 0), pady=6)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=label, font=FONT_LABEL, text_color=COLOR_TEXT_MUTED).pack(anchor="w")
            combo = ctk.CTkComboBox(row, values=options, width=300, height=36, state="readonly")
            combo.set(options[0])
            combo.pack(anchor="w", pady=(4, 0))
            self._mapping_widgets[key] = combo
        self.mapping_frame.grid_columnconfigure((0, 1), weight=1)

        regex_row = ctk.CTkFrame(self.mapping_frame, fg_color="transparent")
        regex_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(regex_row, text="Regex placas (opcional)", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED).pack(anchor="w")
        self.placas_regex_entry = ctk.CTkEntry(regex_row, placeholder_text="Ej: ^[A-Z0-9\\-]{5,10}$", width=650, height=36)
        self.placas_regex_entry.pack(anchor="w", pady=(4, 0))

    def on_dataset_change(self, value=None):
        label = value or self.selector.get()
        dataset_id = self._dataset_label_to_id.get(label)
        columns = self._data_service.get_dataset_columns(dataset_id) if dataset_id else []
        self._render_mapping(columns)
        ds = None
        for item in self._data_service.get_all_datasets():
            if item.get("id") == dataset_id:
                ds = item
                break
        if not ds:
            self.ds_name_value.configure(text="Nombre: N/A")
            self.ds_id_value.configure(text="Dataset ID: N/A")
            self.ds_date_value.configure(text="Fecha de carga: N/A")
            return
        self.ds_name_value.configure(text=f"Nombre: {ds.get('name','')}")
        self.ds_id_value.configure(text=f"Dataset ID: {str(ds.get('id',''))[:8]}")
        fecha = ds.get("date", "N/A")
        self.ds_date_value.configure(text=f"Fecha de carga: {fecha}")

    def run_validation(self):
        import tkinter.messagebox as messagebox
        from datetime import datetime

        label = self.selector.get()
        dataset_id = self._dataset_label_to_id.get(label)
        if not dataset_id:
            messagebox.showwarning("Advertencia", "Por favor, cargue un dataset primero en la sección 'Gestión de Datasets'.")
            return

        start_ts = datetime.now().strftime("%d-%m-%Y %H:%M")
        self.proc_status_value.configure(text="Estado: En proceso")
        self.proc_start_value.configure(text=f"Fecha de inicio: {start_ts}")
        self.proc_end_value.configure(text="Fecha de finalización: N/A")
        self.proc_total_value.configure(text="Total de inconsistencias detectadas: N/A")
        self.btn_view_findings.configure(state="disabled")
        self._last_run_id = None
        self.update_idletasks()

        selected_rule_ids = [rid for rid, cb in self.checkboxes.items() if cb.get()]
        mapping = {}
        for k, combo in self._mapping_widgets.items():
            v = combo.get()
            mapping[k] = None if v == "(sin seleccionar)" else v
        regex = (self.placas_regex_entry.get() or "").strip()
        if regex:
            mapping["placas_regex"] = regex
        try:
            run = self._data_service.run_validation(dataset_id, selected_rule_ids, mapping)
            end_ts = datetime.now().strftime("%d-%m-%Y %H:%M")
            self.proc_status_value.configure(text=f"Estado: {run.get('status','Completado')}")
            self.proc_end_value.configure(text=f"Fecha de finalización: {end_ts}")
            self.proc_total_value.configure(text=f"Total de inconsistencias detectadas: {run.get('inconsistencies','N/A')}")
            self._last_run_id = run.get("id")
            if self._last_run_id:
                self.btn_view_findings.configure(state="normal")
            messagebox.showinfo(
                "Validación completada",
                f"Se ejecutó la validación.\nEjecución: {run['id'][:8]}\nInconsistencias: {run['inconsistencies']}",
            )
        except Exception as e:
            end_ts = datetime.now().strftime("%d-%m-%Y %H:%M")
            self.proc_status_value.configure(text="Estado: Error")
            self.proc_end_value.configure(text=f"Fecha de finalización: {end_ts}")
            messagebox.showerror("Error", f"No se pudo ejecutar la validación:\n{str(e)}")

    def toggle_advanced(self):
        if self.advanced_open:
            self.advanced_frame.pack_forget()
            self.advanced_toggle_btn.configure(text="Opciones avanzadas ▼")
            self.advanced_open = False
        else:
            self.advanced_frame.pack(fill="x", padx=25, pady=(0, 25))
            self.advanced_toggle_btn.configure(text="Opciones avanzadas ▲")
            self.advanced_open = True

    def open_findings_dialog(self):
        import tkinter.messagebox as messagebox

        if not self._last_run_id:
            messagebox.showwarning("Advertencia", "No hay una ejecución reciente para mostrar hallazgos.")
            return
        findings = self._data_service.get_findings(run_id=self._last_run_id)

        dlg = ctk.CTkToplevel(self)
        dlg.title("Hallazgos")
        dlg.geometry("980x560")
        dlg.grab_set()

        header = ctk.CTkFrame(dlg, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text=f"Hallazgos de la ejecución {str(self._last_run_id)[:8]}", font=FONT_HEADING, text_color=COLOR_TEXT_DARK).pack(
            side="left"
        )

        card = ctk.CTkFrame(dlg, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        headers = ["Regla", "Campo", "Valor", "Severidad", "Fila"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=12, pady=(8, 10))
            scroll.grid_columnconfigure(i, weight=1)

        for r_idx, f in enumerate(findings, start=1):
            ctk.CTkLabel(scroll, text=str(f.get("rule_name", "")), font=FONT_LABEL_BOLD).grid(row=r_idx, column=0, sticky="w", padx=12, pady=6)
            ctk.CTkLabel(scroll, text=str(f.get("field", ""))).grid(row=r_idx, column=1, sticky="w", padx=12, pady=6)
            ctk.CTkLabel(scroll, text=str(f.get("value", ""))[:40]).grid(row=r_idx, column=2, sticky="w", padx=12, pady=6)
            ctk.CTkLabel(scroll, text=str(f.get("severity", ""))).grid(row=r_idx, column=3, sticky="w", padx=12, pady=6)
            ctk.CTkLabel(scroll, text=str(f.get("row_index", ""))).grid(row=r_idx, column=4, sticky="w", padx=12, pady=6)

    def get_frame(self) -> ctk.CTkFrame:
        return self


class FindingsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._dataset_label_to_id = {}
        self._run_label_to_id = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Hallazgos Detectados", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        self.select_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.select_card.pack(fill="x", pady=(0, 20))

        row1 = ctk.CTkFrame(self.select_card, fg_color="transparent")
        row1.pack(fill="x", padx=25, pady=(20, 10))
        ctk.CTkLabel(row1, text="Dataset", font=FONT_LABEL_BOLD).pack(side="left")
        self.dataset_selector = ctk.CTkComboBox(self.select_card, values=["No hay datasets disponibles"], width=650, height=40, state="readonly", command=self.on_dataset_change)
        self.dataset_selector.pack(anchor="w", padx=25, pady=(0, 15))

        row2 = ctk.CTkFrame(self.select_card, fg_color="transparent")
        row2.pack(fill="x", padx=25, pady=(0, 10))
        ctk.CTkLabel(row2, text="Ejecución", font=FONT_LABEL_BOLD).pack(side="left")
        self.run_selector = ctk.CTkComboBox(self.select_card, values=["No hay ejecuciones"], width=650, height=40, state="readonly")
        self.run_selector.pack(anchor="w", padx=25, pady=(0, 15))

        btn_row = ctk.CTkFrame(self.select_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=25, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cargar hallazgos", fg_color=COLOR_PRIMARY, command=self.load_findings).pack(side="left")
        ctk.CTkButton(btn_row, text="Generar PDF", fg_color=COLOR_SUCCESS, command=self.generate_pdf).pack(side="left", padx=10)

        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        self.table_scroll = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        datasets = self._data_service.get_all_datasets()
        self._dataset_label_to_id = {}
        ds_values = []
        for ds in datasets:
            label = f"{str(ds['id'])[:8]} - {ds['name']}"
            self._dataset_label_to_id[label] = ds["id"]
            ds_values.append(label)
        if not ds_values:
            ds_values = ["No hay datasets disponibles"]
        self.dataset_selector.configure(values=ds_values)
        self.dataset_selector.set(ds_values[0])
        self.on_dataset_change(ds_values[0])
        self._render_table([])

    def on_dataset_change(self, value=None):
        label = value or self.dataset_selector.get()
        dataset_id = self._dataset_label_to_id.get(label)
        runs = self._data_service.get_runs(dataset_id=dataset_id) if dataset_id else []
        self._run_label_to_id = {}
        run_values = []
        for r in runs:
            rlabel = f"{str(r['id'])[:8]} - {r.get('date','')} {r.get('time','')} ({r.get('inconsistencies',0)} inc.)"
            self._run_label_to_id[rlabel] = r["id"]
            run_values.append(rlabel)
        if not run_values:
            run_values = ["No hay ejecuciones"]
        self.run_selector.configure(values=run_values)
        self.run_selector.set(run_values[0])

    def load_findings(self):
        import tkinter.messagebox as messagebox

        run_label = self.run_selector.get()
        run_id = self._run_label_to_id.get(run_label)
        if not run_id:
            messagebox.showwarning("Advertencia", "No hay una ejecución válida seleccionada.")
            return
        findings = self._data_service.get_findings(run_id=run_id)
        self._render_table(findings)

    def generate_pdf(self):
        import tkinter.messagebox as messagebox

        run_label = self.run_selector.get()
        run_id = self._run_label_to_id.get(run_label)
        if not run_id:
            messagebox.showwarning("Advertencia", "No hay una ejecución válida seleccionada.")
            return
        out_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return
        try:
            self._data_service.export_run_pdf(run_id, out_path)
            messagebox.showinfo("PDF generado", f"Reporte guardado en:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{str(e)}")

    def _render_table(self, findings: list[dict]):
        for w in self.table_scroll.winfo_children():
            w.destroy()

        headers = ["ID", "Regla", "Campo", "Valor", "Severidad", "Fila", "Preview"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(
                row=0, column=i, sticky="w", padx=15, pady=(10, 10)
            )
            self.table_scroll.grid_columnconfigure(i, weight=1)

        for r_idx, f in enumerate(findings, start=1):
            ctk.CTkLabel(self.table_scroll, text=str(f.get("id", ""))[:8]).grid(row=r_idx, column=0, sticky="w", padx=15, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(f.get("rule_name", "")), font=FONT_LABEL_BOLD).grid(
                row=r_idx, column=1, sticky="w", padx=15, pady=6
            )
            ctk.CTkLabel(self.table_scroll, text=str(f.get("field", ""))).grid(row=r_idx, column=2, sticky="w", padx=15, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(f.get("value", ""))[:40]).grid(row=r_idx, column=3, sticky="w", padx=15, pady=6)
            sev = str(f.get("severity", "Alta"))
            sev_color = ACCENT_MEDIUM
            if sev == "Cr\u00edtica":
                sev_color = ACCENT_CRITICAL
            elif sev == "Alta":
                sev_color = COLOR_ERROR
            elif sev == "Baja":
                sev_color = ACCENT_LOW
            badge = ctk.CTkFrame(self.table_scroll, fg_color=sev_color, corner_radius=12)
            badge.grid(row=r_idx, column=4, sticky="w", padx=15, pady=6)
            ctk.CTkLabel(badge, text=sev, font=FONT_SMALL, text_color=COLOR_ON_COLOR).pack(padx=8, pady=1)
            row_index = f.get("row_index", None)
            try:
                row_number = int(row_index) + 2
            except Exception:
                row_number = ""
            ctk.CTkLabel(self.table_scroll, text=str(row_number)).grid(row=r_idx, column=5, sticky="w", padx=15, pady=6)
            ctk.CTkButton(
                self.table_scroll,
                text="Ver",
                width=70,
                height=28,
                fg_color=COLOR_PRIMARY,
                command=lambda ff=f: self._open_preview(ff),
            ).grid(row=r_idx, column=6, sticky="w", padx=15, pady=6)

    def _open_preview(self, finding: dict):
        import tkinter.messagebox as messagebox

        ds_id = str(finding.get("dataset_id", "") or "")
        row_index = finding.get("row_index", None)
        if not ds_id or row_index is None:
            messagebox.showwarning("Sin fila", "Este hallazgo no tiene una fila asociada para previsualizar.")
            return
        try:
            preview = self._data_service.get_dataset_row_preview(ds_id, int(row_index))
        except Exception:
            preview = None
        if not preview:
            messagebox.showerror("No disponible", "No se pudo cargar la fila del archivo para previsualizar.")
            return
        FindingPreviewDialog(self, finding, preview)

    def get_frame(self) -> ctk.CTkFrame:
        return self


class FindingPreviewDialog(ctk.CTkToplevel):
    def __init__(self, master, finding: dict, preview: dict):
        super().__init__(master)
        self.title("Preview de fila")
        self.geometry("900x620")
        self.minsize(820, 520)

        row_index = preview.get("row_index", 0)
        try:
            row_number = int(row_index) + 2
        except Exception:
            row_number = ""
        field = str(finding.get("field", "") or "")
        rule = str(finding.get("rule_name", "") or "")
        desc = str(finding.get("description", "") or "")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(top, text="Preview del error", font=FONT_TITLE).pack(anchor="w")
        ctk.CTkLabel(top, text=f"Regla: {rule}", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(top, text=f"Fila (CSV): {row_number} | Campo: {field}", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED).pack(anchor="w")
        if desc:
            ctk.CTkLabel(top, text=desc, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED, wraplength=860, justify="left").pack(
                anchor="w", pady=(4, 0)
            )

        card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        card.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(16, 8))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Columna", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Valor", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=1, sticky="w")

        body = ctk.CTkScrollableFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)

        row = preview.get("row") or {}
        cols = list(preview.get("columns") or row.keys())
        for i, col in enumerate(cols):
            val = row.get(col, "")
            row_bg = ("#F1F5F9", "#0B1B35") if str(col) == field else "transparent"
            line = ctk.CTkFrame(body, fg_color=row_bg, corner_radius=8)
            line.grid(row=i, column=0, columnspan=2, sticky="ew", padx=6, pady=3)
            line.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(line, text=str(col), font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).grid(row=0, column=0, sticky="w", padx=10, pady=6)
            ctk.CTkLabel(line, text=str(val), font=FONT_LABEL, text_color=COLOR_TEXT_DARK, wraplength=620, justify="left").grid(
                row=0, column=1, sticky="w", padx=10, pady=6
            )

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btns, text="Cerrar", fg_color=COLOR_SECONDARY, command=self.destroy).pack(side="right")

        self.grab_set()
        self.focus_set()


class RecommendationsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._dataset_label_to_id = {}
        self._run_label_to_id = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Recomendaciones del Sistema", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        self.select_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.select_card.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(self.select_card, text="Dataset", font=FONT_LABEL_BOLD).pack(anchor="w", padx=25, pady=(20, 5))
        self.dataset_selector = ctk.CTkComboBox(self.select_card, values=["No hay datasets disponibles"], width=650, height=40, state="readonly", command=self.on_dataset_change)
        self.dataset_selector.pack(anchor="w", padx=25, pady=(0, 15))

        ctk.CTkLabel(self.select_card, text="Ejecución", font=FONT_LABEL_BOLD).pack(anchor="w", padx=25, pady=(0, 5))
        self.run_selector = ctk.CTkComboBox(self.select_card, values=["No hay ejecuciones"], width=650, height=40, state="readonly")
        self.run_selector.pack(anchor="w", padx=25, pady=(0, 15))

        btn_row = ctk.CTkFrame(self.select_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=25, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cargar recomendaciones", fg_color=COLOR_PRIMARY, command=self.load_recommendations).pack(side="left")

        self.card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.card.pack(fill="both", expand=True)
        self.scroll = ctk.CTkScrollableFrame(self.card, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        datasets = self._data_service.get_all_datasets()
        self._dataset_label_to_id = {}
        ds_values = []
        for ds in datasets:
            label = f"{str(ds['id'])[:8]} - {ds['name']}"
            self._dataset_label_to_id[label] = ds["id"]
            ds_values.append(label)
        if not ds_values:
            ds_values = ["No hay datasets disponibles"]
        self.dataset_selector.configure(values=ds_values)
        self.dataset_selector.set(ds_values[0])
        self.on_dataset_change(ds_values[0])
        self._render([])

    def on_dataset_change(self, value=None):
        label = value or self.dataset_selector.get()
        dataset_id = self._dataset_label_to_id.get(label)
        runs = self._data_service.get_runs(dataset_id=dataset_id) if dataset_id else []
        self._run_label_to_id = {}
        run_values = []
        for r in runs:
            rlabel = f"{str(r['id'])[:8]} - {r.get('date','')} {r.get('time','')}"
            self._run_label_to_id[rlabel] = r["id"]
            run_values.append(rlabel)
        if not run_values:
            run_values = ["No hay ejecuciones"]
        self.run_selector.configure(values=run_values)
        self.run_selector.set(run_values[0])

    def load_recommendations(self):
        import tkinter.messagebox as messagebox

        run_label = self.run_selector.get()
        run_id = self._run_label_to_id.get(run_label)
        if not run_id:
            messagebox.showwarning("Advertencia", "No hay una ejecución válida seleccionada.")
            return
        try:
            recs = self._data_service.get_recommendations(run_id)
            self._render(recs)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar recomendaciones:\n{str(e)}")

    def _render(self, recs: list[dict]):
        for w in self.scroll.winfo_children():
            w.destroy()
        headers = ["Regla", "Recomendación"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=20, pady=15)
            self.scroll.grid_columnconfigure(i, weight=1)
        for idx, r in enumerate(recs, start=1):
            ctk.CTkLabel(self.scroll, text=str(r.get("rule_id", "")), font=FONT_LABEL_BOLD).grid(row=idx, column=0, sticky="w", padx=20, pady=10)
            ctk.CTkLabel(self.scroll, text=str(r.get("recommendation", ""))).grid(row=idx, column=1, sticky="w", padx=20, pady=10)

    def get_frame(self) -> ctk.CTkFrame:
        return self


class StatsViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service
        self._dataset_label_to_id: dict[str, str | None] = {"Todos": None}
        self._loading = False

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Estadísticas", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=140, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        self.select_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.select_card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(self.select_card, text="Dataset (opcional)", font=FONT_LABEL_BOLD).pack(anchor="w", padx=25, pady=(18, 5))
        self.dataset_selector = ctk.CTkComboBox(self.select_card, values=["Todos"], width=650, height=40, state="readonly", command=self._on_dataset_select)
        self.dataset_selector.pack(anchor="w", padx=25, pady=(0, 18))

        self.status_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.status_card.pack(fill="x", pady=(0, 20))
        self.status_label = ctk.CTkLabel(self.status_card, text="Cargando...", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED)
        self.status_label.pack(anchor="w", padx=20, pady=16)

        self.main_row = ctk.CTkFrame(self, fg_color="transparent")
        self.main_row.pack(fill="both", expand=True)
        self.main_row.grid_columnconfigure(0, weight=1)
        self.main_row.grid_columnconfigure(1, weight=1)

        self.summary_card = ctk.CTkFrame(self.main_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.summary_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        ctk.CTkLabel(self.summary_card, text="Resumen", font=FONT_LABEL_BOLD).pack(anchor="w", padx=18, pady=(16, 10))
        self.summary_text = ctk.CTkLabel(self.summary_card, text="", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left")
        self.summary_text.pack(anchor="w", padx=18, pady=(0, 16))

        self.runs_card = ctk.CTkFrame(self.main_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.runs_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=10)
        ctk.CTkLabel(self.runs_card, text="Últimas ejecuciones", font=FONT_LABEL_BOLD).pack(anchor="w", padx=18, pady=(16, 10))
        self.runs_scroll = ctk.CTkScrollableFrame(self.runs_card, fg_color="transparent")
        self.runs_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.dataset_selector.set("Todos")
        self.after(50, self.refresh)

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def _on_dataset_select(self, _value=None):
        self.refresh()

    def refresh(self):
        if self._loading:
            return
        self._loading = True
        self.status_label.configure(text="Cargando estadísticas...", text_color=COLOR_TEXT_MUTED)
        for w in self.runs_scroll.winfo_children():
            w.destroy()
        self.summary_text.configure(text="")

        import threading

        ds_label = self.dataset_selector.get()
        dataset_id = self._dataset_label_to_id.get(ds_label)

        def worker():
            try:
                datasets = self._data_service.get_all_datasets()
                counts = self._data_service.get_severity_counts(dataset_id=dataset_id)
                runs = self._data_service.get_runs(dataset_id=dataset_id)
                return {"datasets": datasets, "counts": counts, "runs": runs, "error": None}
            except Exception as e:
                return {"datasets": [], "counts": {"Cr\u00edtica": 0, "Alta": 0, "Media": 0, "Baja": 0}, "runs": [], "error": str(e)}

        def apply_result(result: dict):
            try:
                datasets = result.get("datasets") or []
                self._dataset_label_to_id = {"Todos": None}
                values = ["Todos"]
                for ds in datasets:
                    try:
                        label = f"{str(ds.get('id',''))[:8]} - {ds.get('name','')}"
                        self._dataset_label_to_id[label] = ds.get("id")
                        values.append(label)
                    except Exception:
                        continue
                self.dataset_selector.configure(values=values)
                if self.dataset_selector.get() not in values:
                    self.dataset_selector.set(values[0])

                err = result.get("error")
                if err:
                    self.status_label.configure(text=f"Error: {err}", text_color=COLOR_ERROR)
                    self._loading = False
                    return

                counts = result.get("counts") or {}
                runs = result.get("runs") or []

                total_inc = sum(int(counts.get(k, 0) or 0) for k in ("Cr\u00edtica", "Alta", "Media", "Baja"))
                self.summary_text.configure(
                    text=(
                        f"Inconsistencias totales: {total_inc}\n"
                        f"Críticas: {int(counts.get('Cr\u00edtica', 0) or 0)}\n"
                        f"Altas: {int(counts.get('Alta', 0) or 0)}\n"
                        f"Medias: {int(counts.get('Media', 0) or 0)}\n"
                        f"Bajas: {int(counts.get('Baja', 0) or 0)}\n"
                        f"Ejecuciones: {len(runs)}"
                    )
                )

                headers = ["Run", "Fecha", "Inconsistencias", "Usuario"]
                for i, h in enumerate(headers):
                    ctk.CTkLabel(self.runs_scroll, text=h, font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=10, pady=(10, 10))
                    self.runs_scroll.grid_columnconfigure(i, weight=1)

                shown = 0
                for idx, r in enumerate(runs[:25], start=1):
                    rid = str(r.get("id", ""))[:8]
                    date = str(r.get("date", ""))
                    time = str(r.get("time", ""))
                    inc = str(r.get("inconsistencies", 0))
                    user = str(r.get("user_email", ""))
                    ctk.CTkLabel(self.runs_scroll, text=rid, font=FONT_LABEL_BOLD).grid(row=idx, column=0, sticky="w", padx=10, pady=6)
                    ctk.CTkLabel(self.runs_scroll, text=f"{date} {time}".strip()).grid(row=idx, column=1, sticky="w", padx=10, pady=6)
                    ctk.CTkLabel(self.runs_scroll, text=inc).grid(row=idx, column=2, sticky="w", padx=10, pady=6)
                    ctk.CTkLabel(self.runs_scroll, text=user).grid(row=idx, column=3, sticky="w", padx=10, pady=6)
                    shown += 1

                if shown == 0:
                    ctk.CTkLabel(self.runs_scroll, text="No hay ejecuciones para mostrar.", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED).grid(
                        row=1, column=0, columnspan=4, sticky="w", padx=10, pady=10
                    )

                self.status_label.configure(text="Listo.", text_color=COLOR_TEXT_MUTED)
            finally:
                self._loading = False

        def run_thread():
            result = worker()
            self.after(0, lambda: apply_result(result))

        threading.Thread(target=run_thread, daemon=True).start()


class DatasetHistoryViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Historial de Datasets", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))
        top_row.grid_columnconfigure(0, weight=3)
        top_row.grid_columnconfigure(1, weight=1)

        self.filters_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.filters_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(self.filters_card, text="Filtros", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 10))

        form = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.f_time = ctk.CTkComboBox(form, values=["Seleccionar tiempo", "Hoy", "Últimos 7 días", "Últimos 30 días"], state="readonly", height=36)
        self.f_status = ctk.CTkComboBox(form, values=["Seleccionar Estado", "Cargado", "Procesando", "Error"], state="readonly", height=36)
        self.f_from = ctk.CTkEntry(form, placeholder_text="Desde (dd/mm/yyyy)", height=36)
        self.f_to = ctk.CTkEntry(form, placeholder_text="Hasta (dd/mm/yyyy)", height=36)
        self.f_query = ctk.CTkEntry(form, placeholder_text="Nombre o ID dataset", height=36)

        ctk.CTkLabel(form, text="Tiempo de carga", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.f_time.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Estado", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=1, sticky="w", pady=(0, 4))
        self.f_status.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Desde", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=2, sticky="w", pady=(0, 4))
        self.f_from.grid(row=1, column=2, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Hasta", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=3, sticky="w", pady=(0, 4))
        self.f_to.grid(row=1, column=3, sticky="ew")

        ctk.CTkLabel(form, text="Buscar", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.f_query.grid(row=3, column=0, columnspan=3, sticky="ew", padx=(0, 10))
        ctk.CTkButton(form, text="Buscar", fg_color=COLOR_PRIMARY, height=36, command=self.refresh).grid(row=3, column=3, sticky="ew")

        self.summary_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.summary_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.summary_card, text="Resumen", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=18, pady=(16, 10))
        self.summary_label = ctk.CTkLabel(self.summary_card, text="", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left")
        self.summary_label.pack(anchor="w", padx=18, pady=(0, 16))

        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.table_card, text="Datasets almacenados", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=20, pady=(16, 8)
        )
        self.table_scroll = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.f_time.set("Seleccionar tiempo")
        self.f_status.set("Seleccionar Estado")
        self.refresh()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def refresh(self):
        datasets = self._data_service.get_all_datasets()
        q = (self.f_query.get() or "").strip().lower()
        status = self.f_status.get()
        if status == "Seleccionar Estado":
            status = ""
        if status:
            datasets = [d for d in datasets if str(d.get("status", "")).lower() == status.lower()]
        if q:
            datasets = [d for d in datasets if q in str(d.get("name", "")).lower() or q in str(d.get("id", "")).lower()]

        total = len(datasets)
        total_records = sum(int(d.get("records", 0) or 0) for d in datasets)
        total_folios = sum(int(d.get("folios", d.get("records", 0)) or 0) for d in datasets)
        self.summary_label.configure(text=f"Total de datasets: {total}\nRegistros procesados: {total_records:,}\nFolios en error: 0\nÚltimo: {datasets[0].get('date','')} {datasets[0].get('time','')}" if datasets else "Sin resultados")

        for w in self.table_scroll.winfo_children():
            w.destroy()
        headers = ["ID Dataset", "Nombre", "Tipo", "Fecha carga", "Hora", "Estado", "Registros", "Folios"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=14, pady=(10, 10))
            self.table_scroll.grid_columnconfigure(i, weight=1)
        for idx, d in enumerate(datasets, start=1):
            ctk.CTkLabel(self.table_scroll, text=str(d.get("id", ""))[:8]).grid(row=idx, column=0, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(d.get("name", "")), font=FONT_LABEL_BOLD).grid(row=idx, column=1, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(d.get("type", "CSV"))).grid(row=idx, column=2, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(d.get("date", ""))).grid(row=idx, column=3, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(d.get("time", ""))).grid(row=idx, column=4, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(d.get("status", ""))).grid(row=idx, column=5, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=f"{int(d.get('records', 0) or 0):,}").grid(row=idx, column=6, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=f"{int(d.get('folios', d.get('records', 0)) or 0):,}").grid(row=idx, column=7, sticky="w", padx=14, pady=6)


class ReportHistoryViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Historial de Reportes", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))
        top_row.grid_columnconfigure(0, weight=3)
        top_row.grid_columnconfigure(1, weight=1)

        self.filters_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.filters_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(self.filters_card, text="Filtros", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 10))

        form = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.f_query = ctk.CTkEntry(form, placeholder_text="Número o ID de reporte/run", height=36)
        self.f_status = ctk.CTkComboBox(form, values=["Seleccionar Estado", "Completado", "Error"], state="readonly", height=36)
        self.f_time = ctk.CTkComboBox(form, values=["Seleccionar tiempo", "Hoy", "Últimos 7 días", "Últimos 30 días"], state="readonly", height=36)
        self.f_from = ctk.CTkEntry(form, placeholder_text="Desde (dd/mm/yyyy)", height=36)
        self.f_to = ctk.CTkEntry(form, placeholder_text="Hasta (dd/mm/yyyy)", height=36)

        ctk.CTkLabel(form, text="Número de reporte", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.f_query.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Estado", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=1, sticky="w", pady=(0, 4))
        self.f_status.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Tiempo de carga", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=2, sticky="w", pady=(0, 4))
        self.f_time.grid(row=1, column=2, sticky="ew", padx=(0, 10))
        ctk.CTkLabel(form, text="Desde", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=0, column=3, sticky="w", pady=(0, 4))
        self.f_from.grid(row=1, column=3, sticky="ew")

        ctk.CTkLabel(form, text="Hasta", font=FONT_SMALL, text_color=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.f_to.grid(row=3, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(form, text="Buscar", fg_color=COLOR_PRIMARY, height=36, command=self.refresh).grid(row=3, column=3, sticky="ew")

        self.summary_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.summary_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.summary_card, text="Resumen de Reportes", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=18, pady=(16, 10)
        )
        self.summary_label = ctk.CTkLabel(self.summary_card, text="", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left")
        self.summary_label.pack(anchor="w", padx=18, pady=(0, 16))

        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.table_card, text="Reportes generados", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=20, pady=(16, 8)
        )
        self.table_scroll = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.f_status.set("Seleccionar Estado")
        self.f_time.set("Seleccionar tiempo")
        self.refresh()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def refresh(self):
        reports = []
        try:
            reports = self._data_service.get_reports()
        except Exception:
            reports = []

        q = (self.f_query.get() or "").strip().lower()
        status = self.f_status.get()
        if status == "Seleccionar Estado":
            status = ""
        if status:
            reports = [r for r in reports if str(r.get("status", "")).lower() == status.lower()]
        if q:
            reports = [r for r in reports if q in str(r.get("id", "")).lower() or q in str(r.get("run_id", "")).lower()]

        total = len(reports)
        ok = sum(1 for r in reports if str(r.get("status", "")).lower() == "completado")
        err = total - ok
        last = f"{reports[0].get('generated_at','')}" if reports else "N/A"
        self.summary_label.configure(text=f"Total reportes: {total}\nReportes PDF: {total}\nReportes descargados: {ok}\nÚltimo reporte: {last}\nRD03: N/A")

        for w in self.table_scroll.winfo_children():
            w.destroy()
        headers = ["ID", "Fecha generado", "Estado", "Formato", "Acción"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=14, pady=(10, 10))
            self.table_scroll.grid_columnconfigure(i, weight=1)
        for idx, r in enumerate(reports, start=1):
            ctk.CTkLabel(self.table_scroll, text=str(r.get("id", ""))[:8]).grid(row=idx, column=0, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("generated_at", ""))).grid(row=idx, column=1, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("status", ""))).grid(row=idx, column=2, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("format", "PDF"))).grid(row=idx, column=3, sticky="w", padx=14, pady=6)
            btns = ctk.CTkFrame(self.table_scroll, fg_color="transparent")
            btns.grid(row=idx, column=4, sticky="w", padx=14, pady=6)
            ctk.CTkButton(btns, text="Descargar", width=90, height=28, fg_color=COLOR_PRIMARY, command=lambda rid=r.get("run_id", ""): self._download(rid)).pack(
                side="left", padx=(0, 8)
            )
            ctk.CTkButton(btns, text="Ver detalle", width=90, height=28, fg_color=COLOR_SECONDARY, command=lambda rr=r: self._detail(rr)).pack(
                side="left"
            )

    def _download(self, run_id: str):
        import tkinter.messagebox as messagebox

        if not run_id:
            messagebox.showwarning("Advertencia", "No hay ejecución asociada al reporte.")
            return
        out_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return
        try:
            self._data_service.export_run_pdf(run_id, out_path)
            messagebox.showinfo("PDF generado", f"Reporte guardado en:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{str(e)}")

    def _detail(self, report: dict):
        import tkinter.messagebox as messagebox

        messagebox.showinfo(
            "Detalle de reporte",
            f"Reporte: {str(report.get('id',''))[:8]}\nRun: {str(report.get('run_id',''))[:8]}\nDataset: {report.get('dataset_name','')}\nEstado: {report.get('status','')}\nGenerado: {report.get('generated_at','')}",
        )


class AdminDashboardViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Panel de Administrador", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=120, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")

        self.cards = ctk.CTkFrame(self, fg_color="transparent")
        self.cards.pack(fill="x", pady=(0, 20))
        self.cards.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._admin_values = {}
        for i, (title, key) in enumerate(
            (
                ("Usuarios registrados", "users"),
                ("Datasets cargados", "datasets"),
                ("Validaciones ejecutadas", "validations"),
                ("Reportes generados", "reports"),
            )
        ):
            card = ctk.CTkFrame(self.cards, height=120, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
            card.grid(row=0, column=i, padx=10, sticky="nsew")
            card.grid_propagate(False)
            ctk.CTkLabel(card, text=title, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).pack(pady=(18, 5))
            value_label = ctk.CTkLabel(card, text="0", font=(FONT_FAMILY, 30, "bold"), text_color=COLOR_TEXT_DARK)
            value_label.pack()
            self._admin_values[key] = value_label

        self.activity_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.activity_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.activity_card, text="Actividad reciente del sistema", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(
            anchor="w", padx=20, pady=(16, 8)
        )
        self.activity_scroll = ctk.CTkScrollableFrame(self.activity_card, fg_color="transparent")
        self.activity_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.refresh()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def refresh(self):
        summary = {}
        try:
            summary = self._data_service.get_admin_summary()
        except Exception:
            summary = {"users": 0, "datasets": 0, "validations": 0, "reports": 0}
        for k, label in self._admin_values.items():
            label.configure(text=str(summary.get(k, 0)))

        for w in self.activity_scroll.winfo_children():
            w.destroy()
        rows = []
        try:
            rows = self._data_service.get_activity(limit=50)
        except Exception:
            rows = []
        headers = ["Usuario", "Acción", "Módulo", "Fecha"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.activity_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(
                row=0, column=i, sticky="w", padx=14, pady=(10, 10)
            )
            self.activity_scroll.grid_columnconfigure(i, weight=1)
        for idx, r in enumerate(rows, start=1):
            ctk.CTkLabel(self.activity_scroll, text=str(r.get("user_email", ""))).grid(row=idx, column=0, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.activity_scroll, text=str(r.get("action", ""))).grid(row=idx, column=1, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.activity_scroll, text=str(r.get("module", ""))).grid(row=idx, column=2, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.activity_scroll, text=str(r.get("created_at", ""))[:16]).grid(row=idx, column=3, sticky="w", padx=14, pady=6)


class AdminUsersViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Usuarios", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="🔄 Actualizar", width=140, fg_color=COLOR_PRIMARY, command=self.refresh).pack(side="right")
        ctk.CTkButton(header, text="Nuevo usuario", width=160, fg_color=COLOR_SUCCESS, command=self._open_new_user).pack(side="right", padx=(0, 10))

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))
        top_row.grid_columnconfigure(0, weight=3)
        top_row.grid_columnconfigure(1, weight=1)

        self.filters_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.filters_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(self.filters_card, text="Filtros", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 10))

        form = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.f_query = ctk.CTkEntry(form, placeholder_text="Buscar por email o ID", height=36)
        self.f_role = ctk.CTkComboBox(form, values=["Todos", "admin", "user"], state="readonly", height=36)
        self.f_state = ctk.CTkComboBox(form, values=["Todos", "Activo", "Inactivo"], state="readonly", height=36)
        self.f_query.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        self.f_role.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        self.f_state.grid(row=0, column=3, sticky="ew")
        self.f_role.set("Todos")
        self.f_state.set("Todos")
        ctk.CTkButton(form, text="Buscar", fg_color=COLOR_PRIMARY, height=36, command=self.refresh).grid(row=1, column=3, sticky="e", pady=(12, 0))

        self.summary_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.summary_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.summary_card, text="Resumen", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=18, pady=(16, 10))
        self.summary_label = ctk.CTkLabel(self.summary_card, text="", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left")
        self.summary_label.pack(anchor="w", padx=18, pady=(0, 16))

        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.table_card, text="Usuarios registrados", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 8))
        self.table_scroll = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.refresh()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def refresh(self):
        import tkinter.messagebox as messagebox

        try:
            users = self._data_service.list_users()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            users = []

        q = (self.f_query.get() or "").strip().lower()
        role = self.f_role.get()
        state = self.f_state.get()
        if role == "Todos":
            role = ""
        if state == "Todos":
            state = ""

        if q:
            users = [u for u in users if q in str(u.get("email", "")).lower() or q in str(u.get("id", "")).lower()]
        if role:
            users = [u for u in users if str(u.get("role", "")).lower() == role.lower()]
        if state == "Activo":
            users = [u for u in users if bool(u.get("active", True))]
        elif state == "Inactivo":
            users = [u for u in users if not bool(u.get("active", True))]

        total = len(users)
        active_n = sum(1 for u in users if bool(u.get("active", True)))
        admins = sum(1 for u in users if str(u.get("role", "")).lower() == "admin")
        last = str(users[0].get("created_at", ""))[:16] if users else "N/A"
        self.summary_label.configure(text=f"Total usuarios: {total}\nActivos: {active_n}\nAdmins: {admins}\nÚltimo: {last}")

        for w in self.table_scroll.winfo_children():
            w.destroy()
        headers = ["ID", "Email", "Rol", "Estado", "Creado", "Acciones"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=14, pady=(10, 10))
            self.table_scroll.grid_columnconfigure(i, weight=1)

        for idx, u in enumerate(users, start=1):
            uid = str(u.get("id", ""))
            email = str(u.get("email", ""))
            rol = str(u.get("role", "user"))
            estado = "Activo" if bool(u.get("active", True)) else "Inactivo"
            created = str(u.get("created_at", ""))[:16]

            ctk.CTkLabel(self.table_scroll, text=uid[:8], font=FONT_LABEL_BOLD).grid(row=idx, column=0, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=email).grid(row=idx, column=1, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=rol).grid(row=idx, column=2, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=estado).grid(row=idx, column=3, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=created).grid(row=idx, column=4, sticky="w", padx=14, pady=6)

            btns = ctk.CTkFrame(self.table_scroll, fg_color="transparent")
            btns.grid(row=idx, column=5, sticky="w", padx=14, pady=6)
            ctk.CTkButton(btns, text="Editar", width=70, height=28, fg_color=COLOR_PRIMARY, command=lambda x=u: self._open_edit_user(x)).pack(
                side="left"
            )
            if bool(u.get("active", True)):
                ctk.CTkButton(btns, text="Desactivar", width=95, height=28, fg_color=COLOR_ERROR, command=lambda x=uid: self._toggle_active(x, False)).pack(
                    side="left", padx=8
                )
            else:
                ctk.CTkButton(btns, text="Activar", width=80, height=28, fg_color=COLOR_SUCCESS, command=lambda x=uid: self._toggle_active(x, True)).pack(
                    side="left", padx=8
                )
            ctk.CTkButton(btns, text="Eliminar", width=80, height=28, fg_color=COLOR_WARNING, command=lambda x=uid: self._delete_user(x)).pack(
                side="left"
            )

    def _toggle_active(self, user_id: str, active: bool):
        import tkinter.messagebox as messagebox

        try:
            self._data_service.update_user(user_id, active=active)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _delete_user(self, user_id: str):
        import tkinter.messagebox as messagebox

        if not messagebox.askyesno("Confirmar", "¿Seguro que deseas eliminar este usuario?"):
            return
        try:
            self._data_service.delete_user(user_id)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _open_edit_user(self, user: dict):
        import tkinter.messagebox as messagebox

        uid = str(user.get("id", "")).strip()
        if not uid:
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Editar usuario")
        dlg.geometry("460x420")
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text=f"Usuario {uid[:8]}", font=FONT_HEADING).pack(anchor="w", padx=20, pady=(20, 10))
        ctk.CTkLabel(dlg, text=str(user.get("email", "")), font=FONT_LABEL, text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=20, pady=(0, 10))

        role = ctk.CTkComboBox(dlg, values=["user", "admin"], state="readonly", height=38)
        role.set(str(user.get("role", "user")) or "user")
        role.pack(fill="x", padx=20, pady=(0, 10))

        active_var = ctk.BooleanVar(value=bool(user.get("active", True)))
        active = ctk.CTkCheckBox(dlg, text="Activo", variable=active_var, onvalue=True, offvalue=False)
        active.pack(anchor="w", padx=20, pady=(0, 10))

        pwd = ctk.CTkEntry(dlg, placeholder_text="Nueva contraseña (opcional)", show="*", height=38)
        pwd.pack(fill="x", padx=20, pady=(0, 10))

        def submit():
            try:
                self._data_service.update_user(uid, role=role.get(), active=active_var.get())
                np = (pwd.get() or "").strip()
                if np:
                    self._data_service.reset_user_password(uid, np)
                messagebox.showinfo("Éxito", "Usuario actualizado.")
                dlg.destroy()
                self.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btns, text="Cancelar", fg_color=COLOR_ERROR, command=dlg.destroy).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btns, text="Guardar", fg_color=COLOR_SUCCESS, command=submit).pack(side="right")

        dlg.grab_set()
        dlg.focus_set()

    def _open_new_user(self):
        import tkinter.messagebox as messagebox

        dlg = ctk.CTkToplevel(self)
        dlg.title("Nuevo usuario")
        dlg.geometry("420x360")
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="Crear usuario", font=FONT_HEADING).pack(anchor="w", padx=20, pady=(20, 10))
        email = ctk.CTkEntry(dlg, placeholder_text="Email", height=38)
        email.pack(fill="x", padx=20, pady=(0, 10))
        password = ctk.CTkEntry(dlg, placeholder_text="Contraseña", show="*", height=38)
        password.pack(fill="x", padx=20, pady=(0, 10))
        role = ctk.CTkComboBox(dlg, values=["user", "admin"], state="readonly", height=38)
        role.set("user")
        role.pack(fill="x", padx=20, pady=(0, 10))
        active_var = ctk.BooleanVar(value=True)
        active = ctk.CTkCheckBox(dlg, text="Activo", variable=active_var, onvalue=True, offvalue=False)
        active.pack(anchor="w", padx=20, pady=(0, 10))

        def submit():
            try:
                self._data_service.create_user(email.get(), password.get(), role.get(), active_var.get())
                messagebox.showinfo("Éxito", "Usuario creado.")
                dlg.destroy()
                self.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btns, text="Cancelar", fg_color=COLOR_ERROR, command=dlg.destroy).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btns, text="Crear", fg_color=COLOR_SUCCESS, command=submit).pack(side="right")

        dlg.grab_set()
        dlg.focus_set()


class AdminRulesViewImpl(ctk.CTkFrame, IView):
    def __init__(self, master, data_service: IDataService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._data_service = data_service

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Gestión de Reglas de Validación", font=FONT_TITLE).pack(side="left")
        ctk.CTkButton(header, text="Nuevo regla", width=140, fg_color=COLOR_PRIMARY, command=self._open_new_rule).pack(side="right")

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))
        top_row.grid_columnconfigure(0, weight=3)
        top_row.grid_columnconfigure(1, weight=1)

        self.filters_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.filters_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(self.filters_card, text="Filtros", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 10))
        form = ctk.CTkFrame(self.filters_card, fg_color="transparent")
        form.pack(fill="x", padx=20, pady=(0, 14))
        form.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.f_name = ctk.CTkEntry(form, placeholder_text="Nombre de regla", height=36)
        self.f_type = ctk.CTkEntry(form, placeholder_text="Tipo", height=36)
        self.f_sev = ctk.CTkEntry(form, placeholder_text="Severidad", height=36)
        self.f_state = ctk.CTkComboBox(form, values=["Todos", "Activo", "Inactivo"], state="readonly", height=36)
        self.f_state.set("Todos")
        self.f_name.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.f_type.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.f_sev.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        self.f_state.grid(row=0, column=3, sticky="ew")
        ctk.CTkButton(form, text="Buscar", fg_color=COLOR_PRIMARY, height=36, command=self.refresh).grid(row=1, column=3, sticky="e", pady=(12, 0))

        self.summary_card = ctk.CTkFrame(top_row, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.summary_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.summary_card, text="Resumen de reglas", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=18, pady=(16, 10))
        self.summary_label = ctk.CTkLabel(self.summary_card, text="", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left")
        self.summary_label.pack(anchor="w", padx=18, pady=(0, 16))

        self.table_card = ctk.CTkFrame(self, fg_color=COLOR_WHITE, corner_radius=CARD_RADIUS)
        self.table_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.table_card, text="Reglas registradas", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_DARK).pack(anchor="w", padx=20, pady=(16, 8))
        self.table_scroll = ctk.CTkScrollableFrame(self.table_card, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.refresh()

    def get_frame(self) -> ctk.CTkFrame:
        return self

    def refresh(self):
        rules = self._data_service.get_rules()
        name_q = (self.f_name.get() or "").strip().lower()
        type_q = (self.f_type.get() or "").strip().lower()
        sev_q = (self.f_sev.get() or "").strip().lower()
        state = self.f_state.get()
        if name_q:
            rules = [r for r in rules if name_q in str(r.get("name", "")).lower()]
        if type_q:
            rules = [r for r in rules if type_q in str(r.get("type", "")).lower()]
        if sev_q:
            rules = [r for r in rules if sev_q in str(r.get("severity", "")).lower()]
        if state == "Activo":
            rules = [r for r in rules if bool(r.get("active", True))]
        elif state == "Inactivo":
            rules = [r for r in rules if not bool(r.get("active", True))]

        total = len(rules)
        active = sum(1 for r in rules if bool(r.get("active", True)))
        self.summary_label.configure(text=f"Total reglas: {total}\nReglas activas: {active}\nReglas inactivas: {total - active}")

        for w in self.table_scroll.winfo_children():
            w.destroy()
        headers = ["Regla", "Nombre", "Tipo", "Severidad", "Estado", "Acción"]
        for i, h in enumerate(headers):
            ctk.CTkLabel(self.table_scroll, text=h, font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED).grid(row=0, column=i, sticky="w", padx=14, pady=(10, 10))
            self.table_scroll.grid_columnconfigure(i, weight=1)
        for idx, r in enumerate(rules, start=1):
            rid = str(r.get("id", ""))
            ctk.CTkLabel(self.table_scroll, text=rid, font=FONT_LABEL_BOLD).grid(row=idx, column=0, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("name", ""))).grid(row=idx, column=1, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("type", ""))).grid(row=idx, column=2, sticky="w", padx=14, pady=6)
            ctk.CTkLabel(self.table_scroll, text=str(r.get("severity", ""))).grid(row=idx, column=3, sticky="w", padx=14, pady=6)
            state_text = "Activo" if bool(r.get("active", True)) else "Inactivo"
            ctk.CTkLabel(self.table_scroll, text=state_text).grid(row=idx, column=4, sticky="w", padx=14, pady=6)
            btns = ctk.CTkFrame(self.table_scroll, fg_color="transparent")
            btns.grid(row=idx, column=5, sticky="w", padx=14, pady=6)
            if bool(r.get("active", True)):
                ctk.CTkButton(btns, text="Desactivar", width=90, height=28, fg_color=COLOR_ERROR, command=lambda x=rid: self._toggle(x, False)).pack(side="left")
            else:
                ctk.CTkButton(btns, text="Activar", width=90, height=28, fg_color=COLOR_SUCCESS, command=lambda x=rid: self._toggle(x, True)).pack(side="left")

    def _toggle(self, rid: str, active: bool):
        import tkinter.messagebox as messagebox

        try:
            self._data_service.set_rule_active(rid, active)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _open_new_rule(self):
        import tkinter.messagebox as messagebox

        dlg = ctk.CTkToplevel(self)
        dlg.title("Nueva regla")
        dlg.geometry("520x520")
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="Crear/Actualizar regla", font=FONT_HEADING).pack(anchor="w", padx=20, pady=(20, 10))
        rid = ctk.CTkEntry(dlg, placeholder_text="ID (ej: R001)", height=38)
        rid.pack(fill="x", padx=20, pady=(0, 10))
        name = ctk.CTkEntry(dlg, placeholder_text="Nombre", height=38)
        name.pack(fill="x", padx=20, pady=(0, 10))
        desc = ctk.CTkEntry(dlg, placeholder_text="Descripción", height=38)
        desc.pack(fill="x", padx=20, pady=(0, 10))
        rtype = ctk.CTkEntry(dlg, placeholder_text="Tipo (formato/rango/logica/campos_obligatorios)", height=38)
        rtype.pack(fill="x", padx=20, pady=(0, 10))
        sev = ctk.CTkEntry(dlg, placeholder_text="Severidad (Cr\u00edtica/Alta/Media/Baja)", height=38)
        sev.pack(fill="x", padx=20, pady=(0, 10))
        active_var = ctk.BooleanVar(value=True)
        active = ctk.CTkCheckBox(dlg, text="Activo", variable=active_var, onvalue=True, offvalue=False)
        active.pack(anchor="w", padx=20, pady=(0, 10))

        def submit():
            try:
                self._data_service.create_rule(rid.get(), name.get(), desc.get(), rtype.get(), sev.get(), active_var.get())
                messagebox.showinfo("Éxito", "Regla guardada.")
                dlg.destroy()
                self.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btns, text="Cancelar", fg_color=COLOR_ERROR, command=dlg.destroy).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btns, text="Guardar", fg_color=COLOR_SUCCESS, command=submit).pack(side="right")

        dlg.grab_set()
        dlg.focus_set()
