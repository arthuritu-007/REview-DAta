from __future__ import annotations

import customtkinter as ctk

from login_view import LoginFrame
from main_view import MainApp
from styles import COLOR_BG_LIGHT
from services import DataService
from factories import StandardViewFactory
from database import Database

class Application(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema Review Data")
        self.geometry("1200x800")
        self.db = Database()
        self.data_service = DataService(self.db)
        self.view_factory = StandardViewFactory(self.data_service)
        self.container = ctk.CTkFrame(self, fg_color=COLOR_BG_LIGHT)
        self.container.pack(fill="both", expand=True)
        self.current_frame = None
        self.show_login()

    def show_login(self):
        if self.current_frame:
            self.current_frame.destroy()

        self.current_frame = LoginFrame(
            self.container, on_login_success=self.show_main_app
        )
        self.current_frame.pack(fill="both", expand=True)

    def show_main_app(self):
        if self.current_frame:
            self.current_frame.destroy()

        self.current_frame = MainApp(
            self.container, on_logout=self.show_login, view_factory=self.view_factory
        )
        self.current_frame.pack(fill="both", expand=True)

    def on_closing(self):
        self.db.close()
        self.destroy()

if __name__ == "__main__":
    app = Application()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
