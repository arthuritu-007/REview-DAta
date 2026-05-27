import customtkinter as ctk
import tkinter.messagebox as messagebox

from core.interfaces import IDataService
from ui.animations import animate_widget
from ui.styles import *


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, on_login_success, data_service: IDataService, **kwargs):
        super().__init__(master, **kwargs)
        self.on_login_success = on_login_success
        self._data_service = data_service
        self.configure(fg_color=COLOR_BG_LIGHT)

        self.card = ctk.CTkFrame(self, width=400, height=500, fg_color=COLOR_WHITE, corner_radius=10)
        self.card.place(relx=-1.0, rely=0.5, anchor="center")
        self.card.pack_propagate(False)

        self.logo_frame = ctk.CTkFrame(self.card, width=80, height=80, fg_color=COLOR_PRIMARY, corner_radius=40)
        self.logo_frame.pack(pady=(40, 10))
        self.logo_label = ctk.CTkLabel(self.logo_frame, text="RD", font=("Segoe UI", 32, "bold"), text_color=COLOR_ON_COLOR)
        self.logo_label.place(relx=0.5, rely=0.5, anchor="center")

        self.title_label = ctk.CTkLabel(self.card, text="Sistema Review Data", font=FONT_TITLE, text_color=COLOR_TEXT_DARK)
        self.title_label.pack(pady=(10, 0))

        self.subtitle_label = ctk.CTkLabel(
            self.card, text="Sistema de Detección de Inconsistencias", font=FONT_SUBTITLE, text_color=COLOR_TEXT_MUTED
        )
        self.subtitle_label.pack(pady=(0, 30))

        self.email_label = ctk.CTkLabel(self.card, text="Correo electrónico", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.email_label.pack(anchor="w", padx=40)
        self.email_entry = ctk.CTkEntry(
            self.card,
            placeholder_text="Ingrese su correo electrónico",
            width=320,
            height=40,
            fg_color=COLOR_WHITE,
            border_color="#CCCCCC",
            text_color=COLOR_TEXT_DARK,
        )
        self.email_entry.pack(pady=(5, 15))

        self.password_label = ctk.CTkLabel(self.card, text="Contraseña", font=FONT_LABEL, text_color=COLOR_TEXT_MUTED)
        self.password_label.pack(anchor="w", padx=40)
        self.password_entry = ctk.CTkEntry(
            self.card,
            placeholder_text="Ingrese su contraseña",
            show="*",
            width=320,
            height=40,
            fg_color=COLOR_WHITE,
            border_color="#CCCCCC",
            text_color=COLOR_TEXT_DARK,
        )
        self.password_entry.pack(pady=(5, 30))

        self.login_button = ctk.CTkButton(
            self.card,
            text="Iniciar sesión",
            font=FONT_BUTTON,
            fg_color=COLOR_PRIMARY,
            hover_color="#0069D9",
            width=320,
            height=45,
            corner_radius=5,
            command=self.handle_login,
        )
        self.login_button.pack(pady=(0, 40))

        self.after(100, lambda: animate_widget(self.card, "relx", -1.0, 0.5, duration=600))

    def handle_login(self):
        email = self.email_entry.get()
        password = self.password_entry.get()
        session = self._data_service.authenticate(email, password)
        if not session:
            messagebox.showerror("Credenciales inválidas", "Credenciales inválidas")
            return
        if not self._data_service.set_session(session.get("token", "")):
            messagebox.showerror("Sesión inválida", "No se pudo iniciar sesión. Token inválido.")
            return
        animate_widget(self.card, "relx", 0.5, 2.0, duration=500)
        self.after(550, self.on_login_success)
