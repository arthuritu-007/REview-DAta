## Accesos y conexión a la VPS (Review Data)

### Usuario Administrador (por defecto)

# Correo: `+`

- Contraseña: `admin123`
- Rol: `admin`

### Usuario Normal (seed en BD)

- Correo: `user@reviewdata.local`
- Contraseña: `user123`
- Rol: `user`

### Variables de entorno relacionadas (opcional)

#### Cambiar los accesos por defecto

- `REVIEWDATA_DEFAULT_EMAIL`
- `REVIEWDATA_DEFAULT_PASSWORD`
- `REVIEWDATA_SEED_USER_EMAIL`
- `REVIEWDATA_SEED_USER_PASSWORD`

#### Conexión a PostgreSQL (para que el login use la BD)

- `REVIEWDATA_DB_HOST=TU_ENDPOINT_O_IP_AWS`
- `REVIEWDATA_DB_PORT=5432`
- `REVIEWDATA_DB_USER=reviewdata_user`
- `REVIEWDATA_DB_PASSWORD=TU_PASSWORD_REAL`
- `REVIEWDATA_DB_NAME=reviewdata`

### Dónde se configura la conexión (sin tocar código)

- Opción A (recomendada): ejecuta `run_reviewdata.bat`. Si no hay configuración guardada, pedirá `REVIEWDATA_DB_PASSWORD` y `REVIEWDATA_JWT_SECRET` y luego lo guardará.
- Opción B: crea un archivo `.env` con las variables.

La app busca `.env` en este orden:

1. Carpeta del proyecto (para desarrollo): `C:\...\pro\.env`
2. Carpeta actual de ejecución: `.env`
3. Configuración por usuario (para instalador/betas): `%LOCALAPPDATA%\ReviewData\.env`
4. Configuración por usuario (alternativa): `%APPDATA%\ReviewData\.env`

### Archivos clave (qué hace cada uno)

- `infrastructure/database.py`: abre la conexión a PostgreSQL y crea/asegura las tablas necesarias (`users`, `datasets`, `rules`, `runs`, `findings`, etc.). También crea usuarios seed (admin/user) si la tabla `users` está vacía.
- `services/auth_service.py`: valida credenciales contra la tabla `users` y emite/verifica token JWT.
- `services/data_service.py`: carga datasets, ejecuta validaciones y persiste resultados. El CSV se guarda en PostgreSQL (`datasets.file_bytes`) y además se mantiene una copia cache local por usuario en `%LOCALAPPDATA%\ReviewData\storage\datasets\` para poder abrirlo rápido al validar.
- `run_reviewdata.bat`: inicializa variables de entorno y ejecuta `ReviewData.exe` (o `python main.py` si no hay exe). Guarda la configuración en `%APPDATA%\ReviewData\.env`.

### Errores comunes de conexión (y qué significan)

- `password authentication failed`: la contraseña de `REVIEWDATA_DB_PASSWORD` no coincide con la del usuario `reviewdata_user` en la VPS.
- `no pg_hba.conf entry`: la VPS no está permitiendo tu IP. Se corrige editando `pg_hba.conf` y reiniciando PostgreSQL en el servidor.

### Distribución a betas (exe + instalador con icono)

1. Genera el ejecutable con `build_exe.ps1` (crea `dist\ReviewData\ReviewData.exe`).
2. Compila el instalador usando el script de Inno Setup `ReviewData_Setup.iss`.
3. El instalador crea un acceso directo (icono) que abre `run_reviewdata.bat` para que el beta configure la conexión la primera vez sin editar código.

