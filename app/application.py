import customtkinter as ctk
import os
import threading
import traceback
import time

from infrastructure.database import Database
from services.data_service import DataService
from ui.factories import StandardViewFactory
from ui.login_view import LoginFrame
from ui.main_view import MainApp
from ui.styles import COLOR_BG_LIGHT, COLOR_TEXT_MUTED, FONT_LABEL_BOLD


class Application(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema Review Data")
        self.geometry("1200x800")
        self.container = ctk.CTkFrame(self, fg_color=COLOR_BG_LIGHT)
        self.container.pack(fill="both", expand=True)
        self.current_frame = None
        self._loading = ctk.CTkLabel(self.container, text="Iniciando...", font=FONT_LABEL_BOLD, text_color=COLOR_TEXT_MUTED)
        self._loading.place(relx=0.5, rely=0.5, anchor="center")
        self.update_idletasks()
        self.update()

        self.db = None
        self.data_service = None
        self.view_factory = None
        self._init_started_at = time.monotonic()
        self.after(10, self._start_init)
        self.after(60000, self._init_watchdog)

    def _start_init(self):
        t = threading.Thread(target=self._init_worker, daemon=True)
        t.start()

    def _set_loading_text(self, text: str):
        try:
            if getattr(self, "_loading", None):
                self._loading.configure(text=text)
        except Exception:
            pass

    def _init_worker(self):
        err = None
        err_trace = None
        try:
            self.after(0, lambda: self._set_loading_text("Conectando a la base de datos..."))
            db = Database()
            self.after(0, lambda: self._set_loading_text("Cargando datos..."))
            data_service = DataService(db)
            view_factory = StandardViewFactory(data_service)
            self.after(0, lambda: self._init_done(db, data_service, view_factory, None, None))
            return
        except Exception as e:
            err = e
            err_trace = traceback.format_exc()
        self.after(0, lambda: self._init_done(None, None, None, err, err_trace))

    def _init_watchdog(self):
        if self.db is not None or self.data_service is not None or self.view_factory is not None:
            return
        if not getattr(self, "_loading", None):
            return
        import tkinter.messagebox as messagebox

        elapsed = int((time.monotonic() - (self._init_started_at or time.monotonic())) * 1000)
        log_path = self._write_crash_log(f"Startup timeout: {elapsed}ms\n")
        messagebox.showerror(
            "Error al iniciar",
            "La aplicación tardó demasiado en iniciar.\n\n"
            "Causa común: la PC no puede conectarse a la base de datos (puerto 5432) o la red bloquea la conexión.\n\n"
            f"Log:\n{log_path}",
        )
        try:
            self.destroy()
        except Exception:
            pass

    def _write_crash_log(self, text: str) -> str:
        base_dir = (os.environ.get("LOCALAPPDATA") or "").strip()
        if not base_dir:
            base_dir = (os.environ.get("APPDATA") or "").strip()
        if not base_dir:
            base_dir = os.path.expanduser("~")
        log_dir = os.path.join(base_dir, "ReviewData")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = os.path.dirname(__file__)
        log_path = os.path.join(log_dir, "crash.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(text or "")
        except Exception:
            log_path = os.path.join(os.path.dirname(__file__), "crash.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(text or "")
        return log_path

    def _init_done(self, db, data_service, view_factory, err: Exception | None, err_trace: str | None):
        if getattr(self, "_loading", None):
            try:
                self._loading.destroy()
            except Exception:
                pass
            self._loading = None

        if err is not None:
            import tkinter.messagebox as messagebox

            log_path = self._write_crash_log(err_trace or str(err))
            messagebox.showerror("Error al iniciar", f"Ocurrió un error al iniciar la aplicación.\n\nLog:\n{log_path}\n\nDetalle:\n{str(err)}")
            try:
                self.destroy()
            except Exception:
                pass
            return

        self.db = db
        self.data_service = data_service
        self.view_factory = view_factory
        self.show_login()

    def show_login(self):
        if self.current_frame:
            self.current_frame.destroy()
        if self.data_service:
            self.data_service.set_session("")
        self.current_frame = LoginFrame(self.container, on_login_success=self.show_main_app, data_service=self.data_service)
        self.current_frame.pack(fill="both", expand=True)

    def show_main_app(self):
        if self.current_frame:
            self.current_frame.destroy()
        self.current_frame = MainApp(self.container, on_logout=self.show_login, view_factory=self.view_factory, data_service=self.data_service)
        self.current_frame.pack(fill="both", expand=True)

    def on_closing(self):
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass
        self.destroy()
