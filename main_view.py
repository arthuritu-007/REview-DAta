from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

import styles as styles
from interfaces import IViewFactory
from animations import animate_widget

class MainApp(ctk.CTkFrame):
    """Refactored MainApp following SOLID (Dependency Inversion) and Abstract Factory."""

    def __init__(
        self,
        master,
        on_logout: Callable[[], None],
        view_factory: IViewFactory,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.on_logout = on_logout
        self._view_factory = view_factory
        self.configure(fg_color=styles.COLOR_BG_LIGHT)

        # Sidebar
        self.sidebar = ctk.CTkFrame(
            self, width=260, fg_color=styles.COLOR_SIDEBAR, corner_radius=0
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo/Title area
        logo_area = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_area.pack(pady=40, padx=20, fill="x")
        
        rd_logo = ctk.CTkFrame(
            logo_area,
            width=40,
            height=40,
            fg_color=styles.COLOR_PRIMARY,
            corner_radius=20,
        )
        rd_logo.pack(side="left")
        ctk.CTkLabel(
            rd_logo,
            text="RD",
            font=(styles.FONT_FAMILY, 16, "bold"),
            text_color=styles.COLOR_WHITE,
        ).place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(
            logo_area,
            text="Review Data",
            font=styles.FONT_SUBTITLE,
            text_color=styles.COLOR_TEXT_LIGHT,
        ).pack(side="left", padx=15)

        # Nav Buttons
        self.nav_buttons = {}
        nav_items = [
            ("Inicio", "home", "🏠"),
            ("Cargar Dataset", "dataset", "📂"),
            ("Ejecutar Validación", "validation", "⚙️"),
            ("Hallazgos", "findings", "🔍"),
            ("Recomendaciones", "recommendations", "💡"),
            ("Estadísticas", "stats", "📊")
        ]

        for text, key, icon in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}  {text}",
                font=styles.FONT_SIDEBAR,
                fg_color="transparent",
                hover_color=styles.COLOR_SIDEBAR_HOVER,
                anchor="w",
                height=50,
                corner_radius=8,
                command=lambda k=key: self.switch_tab(k),
            )
            btn.pack(fill="x", padx=15, pady=4)
            self.nav_buttons[key] = btn

        # Bottom section
        ctk.CTkFrame(self.sidebar, height=1, fg_color=styles.COLOR_SIDEBAR_HOVER).pack(
            side="bottom", fill="x", pady=(0, 80)
        )
        
        self.logout_btn = ctk.CTkButton(
            self.sidebar,
            text="  🚪  Cerrar Sesión",
            font=styles.FONT_SIDEBAR,
            fg_color="transparent",
            hover_color=styles.COLOR_ERROR,
            anchor="w",
            height=50,
            corner_radius=8,
            command=self.on_logout,
        )
        self.logout_btn.pack(side="bottom", fill="x", padx=15, pady=20)

        # Content Area
        self.content_container = ctk.CTkFrame(self, fg_color=styles.COLOR_BG_LIGHT)
        self.content_container.pack(side="right", fill="both", expand=True, padx=40, pady=40)

        self.active_tab_key = None
        self.active_tab_view = None
        self.tabs_cache = {}
        
        self.switch_tab("home")

    def switch_tab(self, key: str) -> None:
        if key == self.active_tab_key:
            return

        # Update sidebar visual state
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=styles.COLOR_PRIMARY, font=styles.FONT_SIDEBAR_BOLD)
            else:
                btn.configure(fg_color="transparent", font=styles.FONT_SIDEBAR)

        # 1. Animación de salida de la vista actual
        if self.active_tab_view:
            old_view_frame = self.active_tab_view.get_frame()
            # En lugar de solo pack_forget, animamos su salida
            animate_widget(old_view_frame, 'relx', 0, -1.5, duration=300)
            self.after(350, old_view_frame.pack_forget)

        # 2. Crear y animar la entrada de la nueva vista
        if key not in self.tabs_cache:
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
            else: 
                placeholder_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
                ctk.CTkLabel(placeholder_frame, text="Próximamente", font=styles.FONT_TITLE).pack(pady=100)

                class _PlaceholderView:
                    def __init__(self, frame: ctk.CTkFrame):
                        self._frame = frame

                    def get_frame(self) -> ctk.CTkFrame:
                        return self._frame

                self.tabs_cache[key] = _PlaceholderView(placeholder_frame)

        self.active_tab_view = self.tabs_cache[key]
        new_view_frame = self.active_tab_view.get_frame()
        
        # Primero pack para que exista en el layout, luego place para animar
        new_view_frame.pack(fill="both", expand=True)
        new_view_frame.place(relx=1.5, rely=0, relwidth=1, relheight=1)
        new_view_frame.lift()
        
        self.after(50, lambda: animate_widget(new_view_frame, 'relx', 1.5, 0, duration=300))

        self.active_tab_key = key
