# Stack Tecnológico - Review Data

Este documento detalla las tecnologías utilizadas en la aplicación web **Review Data**, diseñada para la observabilidad y validación de calidad de datos en el sector transporte.

## **Frontend**
- **Framework:** [React 18](https://reactjs.org/) con [TypeScript](https://www.typescriptlang.org/).
- **Build Tool:** [Vite](https://vitejs.dev/) para un desarrollo ultrarrápido y bundling optimizado.
- **Routing:** [react-router-dom](https://reactrouter.com/) para la navegación SPA (Single Page Application).
- **Estilos:** CSS3 Custom con variables para temas oscuros y animaciones avanzadas (Glow effects, transitions, skeletons).
- **Componentes:** Arquitectura basada en componentes funcionales y Hooks.
- **Gráficas:** [Recharts](https://recharts.org/) para visualización de estadísticas y tendencias IA.

## **Backend**
- **Lenguaje:** [Python 3.10+](https://www.python.org/).
- **Framework API:** [FastAPI](https://fastapi.tiangolo.com/) (Asíncrono, basado en Pydantic).
- **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/) con soporte para hot-reload.
- **Procesamiento de Datos:** [Pandas](https://pandas.pydata.org/) para análisis de CSV y validación de reglas.
- **Seguridad:** [PyJWT](https://pyjwt.readthedocs.io/) para autenticación basada en tokens (JWT).

## **Base de Datos e Infraestructura**
- **Motor DB:** [PostgreSQL](https://www.postgresql.org/) alojado en VPS.
- **Pool de Conexiones:** `psycopg2` con `ThreadedConnectionPool`.
- **Almacenamiento:** Sistema híbrido (Metadatos en DB + Archivos CSV en disco/PostgreSQL Large Objects).
- **Reportes:** [FPDF2](https://py-pdf.github.io/fpdf2/) para generación dinámica de reportes PDF con soporte para tablas complejas.

## **Capa de Inteligencia Artificial (AI)**
- **Arquitectura:** Capa AI Determinística integrada en el flujo de validación.
- **Módulos IA:**
  - Intent Parser para Natural Language Queries.
  - Generador de Insights basado en heurísticas operativas.
  - Drift Detection (Detección de desviaciones entre runs).
  - Auto-generated Expectations (Sugerencia de reglas mediante profiling).
  - Business Impact Analysis (Traducción de errores técnicos a impacto de negocio).

## **Estructura del Proyecto**
- `/web/frontend`: Código fuente de la interfaz de usuario.
- `/web/backend`: Endpoints de la API y lógica de servidor.
- `/services`: Lógica de negocio core ([data_service.py](file:///c:/Users/domin/Documents/trae_projects/pro/services/data_service.py)).
- `/core`: Validadores, reglas y motores de reportes ([pdf_report.py](file:///c:/Users/domin/Documents/trae_projects/pro/core/reports/pdf_report.py)).
- `/infrastructure`: Conexiones a base de datos y utilidades ([database.py](file:///c:/Users/domin/Documents/trae_projects/pro/infrastructure/database.py)).
