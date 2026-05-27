# Guía de Instalación - Review Data

Este documento detalla los pasos necesarios para instalar y configurar el entorno de desarrollo de **Review Data**.

## Requisitos Previos

Antes de comenzar, asegúrate de tener instalado:

1. **Python 3.10+**: [Descargar Python](https://www.python.org/downloads/)
2. **Node.js 18+ y npm**: [Descargar Node.js](https://nodejs.org/)
3. **PostgreSQL**: [Descargar PostgreSQL](https://www.postgresql.org/download/)
4. **Git**: [Descargar Git](https://git-scm.com/)

---

## Pasos de Instalación

### 1. Clonar el Repositorio
```bash
git clone https://github.com/arthuritu-007/REview-DAta.git
cd REview-DAta
```

### 2. Configuración del Backend (Python)
Se recomienda el uso de un entorno virtual para mantener las dependencias aisladas.

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows:
.\venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configuración del Frontend (React)
```bash
cd web/frontend
npm install
cd ../..
```

### 4. Configuración de Variables de Entorno
Crea un archivo `.env` en la raíz del proyecto basado en el archivo `.env.example`.

```bash
cp .env.example .env
```

Edita el archivo `.env` con tus credenciales de PostgreSQL:
```env
REVIEWDATA_DB_HOST=tu_host_vps_o_localhost
REVIEWDATA_DB_PORT=5432
REVIEWDATA_DB_NAME=reviewdata
REVIEWDATA_DB_USER=postgres
REVIEWDATA_DB_PASSWORD=tu_password
```

---

## Inicialización Automática
Para facilitar el proceso en Windows, puedes ejecutar el script de configuración automática:
```powershell
.\setup_env.ps1
```
Este script instalará las dependencias de Python y Node.js automáticamente.
