from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

import styles as styles
from animations import animate_widget

class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login_success: Callable[[], None], **kwargs):
        super().__init__(master, **kwargs)
        self.on_login_success = on_login_success
        self.configure(fg_color=styles.COLOR_BG_LIGHT)

        # Card container
        self.card = ctk.CTkFrame(
            self, width=400, height=500, fg_color=styles.COLOR_WHITE, corner_radius=10
        )
        # Iniciar fuera de la pantalla a la izquierda (relx=-1.0)
        self.card.place(relx=-1.0, rely=0.5, anchor="center")
        self.card.pack_propagate(False)

        # Logo RD
        self.logo_frame = ctk.CTkFrame(
            self.card,
            width=80,
            height=80,
            fg_color=styles.COLOR_PRIMARY,
            corner_radius=40,
        )
        self.logo_frame.pack(pady=(40, 10))
        self.logo_label = ctk.CTkLabel(
            self.logo_frame,
            text="RD",
            font=("Segoe UI", 32, "bold"),
            text_color=styles.COLOR_WHITE,
        )
        self.logo_label.place(relx=0.5, rely=0.5, anchor="center")

        # Titles
        self.title_label = ctk.CTkLabel(
            self.card,
            text="Sistema Review Data",
            font=styles.FONT_TITLE,
            text_color=styles.COLOR_TEXT_DARK,
        )
        self.title_label.pack(pady=(10, 0))
        
        self.subtitle_label = ctk.CTkLabel(
            self.card,
            text="Sistema de Detección de Inconsistencias",
            font=styles.FONT_SUBTITLE,
            text_color=styles.COLOR_TEXT_MUTED,
        )
        self.subtitle_label.pack(pady=(0, 30))

        # Email field
        self.email_label = ctk.CTkLabel(
            self.card,
            text="Correo electrónico",
            font=styles.FONT_LABEL,
            text_color=styles.COLOR_TEXT_MUTED,
        )
        self.email_label.pack(anchor="w", padx=40)
        self.email_entry = ctk.CTkEntry(self.card, placeholder_text="Ingrese su correo electrónico", 
                                        width=320, height=40, fg_color=styles.COLOR_WHITE, border_color="#CCCCCC", 
                                        text_color=styles.COLOR_TEXT_DARK)
        self.email_entry.pack(pady=(5, 15))

        # Password field
        self.password_label = ctk.CTkLabel(
            self.card,
            text="Contraseña",
            font=styles.FONT_LABEL,
            text_color=styles.COLOR_TEXT_MUTED,
        )
        self.password_label.pack(anchor="w", padx=40)
        self.password_entry = ctk.CTkEntry(self.card, placeholder_text="Ingrese su contraseña", 
                                          show="*", width=320, height=40, fg_color=styles.COLOR_WHITE, 
                                          border_color="#CCCCCC", text_color=styles.COLOR_TEXT_DARK)
        self.password_entry.pack(pady=(5, 30))

        # Login Button
        self.login_button = ctk.CTkButton(
            self.card,
            text="Iniciar sesión",
            font=styles.FONT_BUTTON,
            fg_color=styles.COLOR_PRIMARY,
            hover_color="#0069D9",
            width=320,
            height=45,
            corner_radius=5,
            command=self.handle_login,
        )
        self.login_button.pack(pady=(0, 40))

        # Animación de entrada: deslizar desde la izquierda al centro
        self.after(100, lambda: animate_widget(self.card, 'relx', -1.0, 0.5, duration=600))

    def handle_login(self):
        # Animación de salida: deslizar hacia la derecha fuera de la pantalla
        animate_widget(self.card, 'relx', 0.5, 2.0, duration=500)
        # Esperar a que termine la animación para mostrar la app principal
        self.after(550, self.on_login_success)
