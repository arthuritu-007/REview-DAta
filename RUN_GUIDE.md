# Guía de Ejecución - Review Data

Esta guía explica cómo poner en marcha tanto el servidor Backend como la aplicación Frontend.

## Ejecución en Desarrollo

Para que la aplicación funcione, ambos servidores (Backend y Frontend) deben estar corriendo simultáneamente.

### 1. Arrancar el Backend (FastAPI)
Desde la raíz del proyecto, asegúrate de tener el entorno virtual activado y ejecuta:

```bash
python -m uvicorn web.backend.main:app --reload --host 0.0.0.0 --port 8000
```
- **API:** [http://localhost:8000](http://localhost:8000)
- **Documentación (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Arrancar el Frontend (Vite + React)
En una nueva terminal, navega a la carpeta del frontend y ejecuta:

```bash
cd web/frontend
npm run dev
```
- **Aplicación Web:** [http://localhost:5173](http://localhost:5173)

---

## Ejecución Simplificada (Windows)
Puedes usar el archivo por lotes incluido en la raíz para arrancar ambos servicios rápidamente (siempre que el entorno esté configurado):

```bash
.\run_reviewdata.bat
```

## Notas Adicionales
- Asegúrate de que tu base de datos PostgreSQL esté activa y accesible según la configuración en tu archivo `.env`.
- El servidor de desarrollo de Vite tiene habilitado un proxy hacia el puerto 8000 para las peticiones a la API.
