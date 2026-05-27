from app.application import Application


def main():
    app = Application()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import os
        import traceback
        import tkinter.messagebox as messagebox

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
                f.write(traceback.format_exc())
        except Exception:
            log_path = os.path.join(os.path.dirname(__file__), "crash.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        messagebox.showerror("Error al iniciar", f"Ocurrió un error al iniciar la aplicación.\n\nLog:\n{log_path}")
