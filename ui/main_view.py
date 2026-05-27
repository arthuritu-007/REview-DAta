import customtkinter as ctk

from core.interfaces import IViewFactory
from ui.animations import animate_widget
from ui.styles import *


class MainApp(ctk.CTkFrame):
    def __init__(self, master, on_logout, view_factory: IViewFactory, data_service, **kwargs):
        super().__init__(master, **kwargs)
        self.on_logout = on_logout
        self._view_factory = view_factory
        self._data_service = data_service
        self.configure(fg_color=COLOR_BG_LIGHT)

        self.sidebar = ctk.CTkFrame(self, width=260, fg_color=COLOR_SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        logo_area = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_area.pack(pady=40, padx=20, fill="x")

        rd_logo = ctk.CTkFrame(logo_area, width=40, height=40, fg_color=COLOR_PRIMARY, corner_radius=20)
        rd_logo.pack(side="left")
        ctk.CTkLabel(rd_logo, text="RD", font=(FONT_FAMILY, 16, "bold"), text_color=COLOR_ON_COLOR).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(logo_area, text="Review Data", font=FONT_SUBTITLE, text_color=COLOR_TEXT_LIGHT).pack(side="left", padx=15)

        self.nav_buttons = {}
        user = self._data_service.get_current_user() or {}
        is_admin = str(user.get("role", "user")) == "admin"
        if is_admin:
            nav_items = [
                ("Dashboard Admin", "admin_dashboard", "🏠"),
                ("Usuarios", "admin_users", "👤"),
                ("Reglas", "admin_rules", "📋"),
                ("Historial Dataset", "dataset_history", "🗂️"),
                ("Historial Reporte", "report_history", "📄"),
            ]
        else:
            nav_items = [
                ("Inicio", "home", "🏠"),
                ("Cargar Dataset", "dataset", "📂"),
                ("Ejecutar Validación", "validation", "⚙️"),
                ("Hallazgos", "findings", "🔍"),
                ("Recomendaciones", "recommendations", "💡"),
                ("Estadísticas", "stats", "📊"),
                ("Historial Dataset", "dataset_history", "🗂️"),
                ("Historial Reporte", "report_history", "📄"),
            ]

        for text, key, icon in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}  {text}",
                font=FONT_SIDEBAR,
                fg_color="transparent",
                hover_color=COLOR_SIDEBAR_HOVER,
                anchor="w",
                height=50,
                corner_radius=8,
                command=lambda k=key: self.switch_tab(k),
            )
            btn.pack(fill="x", padx=15, pady=4)
            self.nav_buttons[key] = btn

        self.dark_mode_var = ctk.BooleanVar(value=ctk.get_appearance_mode() == "Dark")
        theme_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        theme_row.pack(side="bottom", fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(theme_row, text="Modo oscuro", font=FONT_SMALL, text_color=COLOR_TEXT_LIGHT).pack(side="left")
        ctk.CTkSwitch(theme_row, text="", variable=self.dark_mode_var, command=self._toggle_theme).pack(side="right")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLOR_SIDEBAR_HOVER).pack(side="bottom", fill="x", pady=(0, 10))

        self.logout_btn = ctk.CTkButton(
            self.sidebar,
            text="  🚪  Cerrar Sesión",
            font=FONT_SIDEBAR,
            fg_color="transparent",
            hover_color=COLOR_ERROR,
            anchor="w",
            height=50,
            corner_radius=8,
            command=self.on_logout,
        )
        self.logout_btn.pack(side="bottom", fill="x", padx=15, pady=20)

        self.content_container = ctk.CTkFrame(self, fg_color=COLOR_BG_LIGHT)
        self.content_container.pack(side="right", fill="both", expand=True, padx=25, pady=25)

        self.active_tab_key = None
        self.active_tab_view = None
        self.tabs_cache = {}

        self.switch_tab("admin_dashboard" if is_admin else "home")

    def _toggle_theme(self):
        set_dark_mode(bool(self.dark_mode_var.get()))

    def switch_tab(self, key):
        if key == self.active_tab_key:
            return

        if key == "stats" and key in self.tabs_cache:
            try:
                old = self.tabs_cache.pop(key)
                frame = old.get_frame()
                frame.destroy()
            except Exception:
                pass

        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=COLOR_PRIMARY, font=FONT_SIDEBAR_BOLD)
            else:
                btn.configure(fg_color="transparent", font=FONT_SIDEBAR)

        if self.active_tab_view:
            old_view_frame = self.active_tab_view.get_frame()
            try:
                animate_widget(old_view_frame, "relx", 0, -1.5, duration=300)
            except Exception:
                pass
            self.after(350, old_view_frame.place_forget)

        if key not in self.tabs_cache:
            try:
                if key == "home":
                    self.tabs_cache[key] = self._view_factory.create_dashboard(self.content_container)
                elif key == "dataset":
                    self.tabs_cache[key] = self._view_factory.create_dataset_view(self.content_container)
                elif key == "validation":
                    self.tabs_cache[key] = self._view_factory.create_validation_view(self.content_container)
                elif key == "findings":
                    self.tabs_cache[key] = self._view_factory.create_findings_view(self.content_container)
                elif key == "recommendations":
                    self.tabs_cache[key] = self._view_factory.create_recommendations_view(self.content_container)
                elif key == "stats":
                    self.tabs_cache[key] = self._view_factory.create_stats_view(self.content_container)
                elif key == "dataset_history":
                    from ui.views_impl import DatasetHistoryViewImpl

                    self.tabs_cache[key] = DatasetHistoryViewImpl(self.content_container, self._data_service)
                elif key == "report_history":
                    from ui.views_impl import ReportHistoryViewImpl

                    self.tabs_cache[key] = ReportHistoryViewImpl(self.content_container, self._data_service)
                elif key == "admin_dashboard":
                    from ui.views_impl import AdminDashboardViewImpl

                    self.tabs_cache[key] = AdminDashboardViewImpl(self.content_container, self._data_service)
                elif key == "admin_users":
                    from ui.views_impl import AdminUsersViewImpl

                    self.tabs_cache[key] = AdminUsersViewImpl(self.content_container, self._data_service)
                elif key == "admin_rules":
                    from ui.views_impl import AdminRulesViewImpl

                    self.tabs_cache[key] = AdminRulesViewImpl(self.content_container, self._data_service)
                else:
                    placeholder_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
                    ctk.CTkLabel(placeholder_frame, text="Próximamente", font=FONT_TITLE).pack(pady=100)
                    placeholder = type("Placeholder", (), {"get_frame": lambda self: placeholder_frame})()
                    self.tabs_cache[key] = placeholder
            except Exception as e:
                error_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
                ctk.CTkLabel(error_frame, text="Error al abrir la pantalla", font=FONT_TITLE, text_color=COLOR_ERROR).pack(pady=(60, 10))
                ctk.CTkLabel(error_frame, text=str(e), font=FONT_LABEL, text_color=COLOR_TEXT_MUTED, justify="left", wraplength=900).pack(padx=40, pady=(0, 40))
                placeholder = type("Placeholder", (), {"get_frame": lambda self: error_frame})()
                self.tabs_cache[key] = placeholder

        self.active_tab_view = self.tabs_cache[key]
        new_view_frame = self.active_tab_view.get_frame()
        new_view_frame.place(relx=1.5, rely=0, relwidth=1, relheight=1)
        new_view_frame.lift()
        def _show_new():
            try:
                animate_widget(new_view_frame, "relx", 1.5, 0, duration=300)
            except Exception:
                try:
                    new_view_frame.place_configure(relx=0)
                except Exception:
                    pass

        self.after(50, _show_new)
        self.after(450, lambda: new_view_frame.place_configure(relx=0))

        self.active_tab_key = key
