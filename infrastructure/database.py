import os
import socket
import sys
import uuid

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql


class Database:
    def _is_invalid_host_value(self, value: str) -> bool:
        v = (value or "").strip().lower()
        if not v:
            return True
        if v.startswith("194.238."):
            return True
        if v == "localhost":
            return False
        return "." not in v

    def _unset_env_if_invalid(self):
        host = os.environ.get("REVIEWDATA_DB_HOST")
        if host is not None and self._is_invalid_host_value(host):
            os.environ.pop("REVIEWDATA_DB_HOST", None)

        port = (os.environ.get("REVIEWDATA_DB_PORT") or "").strip()
        if port and not port.isdigit():
            os.environ.pop("REVIEWDATA_DB_PORT", None)

        user = os.environ.get("REVIEWDATA_DB_USER")
        if user is not None and not str(user).strip():
            os.environ.pop("REVIEWDATA_DB_USER", None)

        dbname = os.environ.get("REVIEWDATA_DB_NAME")
        if dbname is not None and not str(dbname).strip():
            os.environ.pop("REVIEWDATA_DB_NAME", None)

        sslmode = (os.environ.get("REVIEWDATA_DB_SSLMODE") or "").strip().lower()
        host_now = (os.environ.get("REVIEWDATA_DB_HOST") or "").strip().lower()
        if sslmode == "require" and host_now and ".rds.amazonaws.com" not in host_now:
            os.environ.pop("REVIEWDATA_DB_SSLMODE", None)

    def _load_env_file(self, path: str):
        p = (path or "").strip()
        if not p or not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                for raw in f.readlines():
                    line = (raw or "").strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = (k or "").strip()
                    v = (v or "").strip().strip("'").strip('"')
                    if not k:
                        continue
                    os.environ.setdefault(k, v)
        except Exception:
            return

    def __init__(self):
        self.last_error = None
        self._unset_env_if_invalid()
        exe_dir = ""
        try:
            exe_dir = os.path.dirname(sys.executable or "")
        except Exception:
            exe_dir = ""
        if exe_dir:
            self._load_env_file(os.path.join(exe_dir, ".env"))
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self._load_env_file(os.path.join(root_dir, ".env"))
        self._load_env_file(os.path.join(os.getcwd(), ".env"))
        local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
        roaming_app_data = (os.environ.get("APPDATA") or "").strip()
        if local_app_data:
            self._load_env_file(os.path.join(local_app_data, "ReviewData", ".env"))
        if roaming_app_data:
            self._load_env_file(os.path.join(roaming_app_data, "ReviewData", ".env"))
        self.conn_params = {
            "host": os.environ.get("REVIEWDATA_DB_HOST", "localhost").strip(),
            "port": os.environ.get("REVIEWDATA_DB_PORT", "5432").strip(),
            "user": os.environ.get("REVIEWDATA_DB_USER", "postgres").strip(),
            "password": os.environ.get("REVIEWDATA_DB_PASSWORD", ""),
            "dbname": os.environ.get("REVIEWDATA_DB_NAME", "reviewdata").strip(),
        }
        ct = (os.environ.get("REVIEWDATA_DB_CONNECT_TIMEOUT") or "").strip()
        if not ct:
            ct = "4"
        if ct.isdigit():
            self.conn_params["connect_timeout"] = int(ct)
        st = (os.environ.get("REVIEWDATA_DB_STATEMENT_TIMEOUT_MS") or "").strip()
        if not st:
            st = "30000"
        lt = (os.environ.get("REVIEWDATA_DB_LOCK_TIMEOUT_MS") or "").strip()
        if not lt:
            lt = "30000"
        if st.isdigit() and lt.isdigit():
            self.conn_params["options"] = f"-c statement_timeout={int(st)} -c lock_timeout={int(lt)}"
        host = str(self.conn_params.get("host") or "").lower()
        sslmode = (os.environ.get("REVIEWDATA_DB_SSLMODE") or "").strip()
        if not sslmode and ".rds.amazonaws.com" in host:
            sslmode = "require"
        if sslmode.strip().lower() == "require" and ".rds.amazonaws.com" not in host:
            sslmode = ""
        if sslmode:
            self.conn_params["sslmode"] = sslmode
        pool_enabled = (os.environ.get("REVIEWDATA_DB_POOL_ENABLED") or "").strip()
        if not pool_enabled:
            pool_enabled = "1"
        self.pool_enabled = pool_enabled not in ("0", "false", "no", "off")
        minc = (os.environ.get("REVIEWDATA_DB_POOL_MINCONN") or "").strip() or "1"
        maxc = (os.environ.get("REVIEWDATA_DB_POOL_MAXCONN") or "").strip() or "10"
        try:
            self.pool_minconn = max(1, int(minc))
        except Exception:
            self.pool_minconn = 1
        try:
            self.pool_maxconn = max(self.pool_minconn, int(maxc))
        except Exception:
            self.pool_maxconn = max(self.pool_minconn, 10)

        self.pool = None
        self.conn = None
        self._schema_mode = False
        self.connect()
        self.ensure_schema()

    def connect(self):
        forced_enc = (os.environ.get("REVIEWDATA_PGCLIENTENCODING") or "").strip()
        if forced_enc:
            os.environ["PGCLIENTENCODING"] = forced_enc
        else:
            os.environ.setdefault("PGCLIENTENCODING", "UTF8")
        host = str(self.conn_params.get("host") or "").strip()
        port = str(self.conn_params.get("port") or "").strip()
        timeout_s = self.conn_params.get("connect_timeout", 8)
        try:
            timeout_s = int(timeout_s)
        except Exception:
            timeout_s = 8
        if host and host.lower() not in ("localhost", "127.0.0.1") and port.isdigit():
            try:
                with socket.create_connection((host, int(port)), timeout=timeout_s):
                    pass
            except Exception as e:
                self.last_error = e
                raise RuntimeError(
                    "No se pudo conectar a PostgreSQL.\n"
                    f"Destino: {host}:{port}\n"
                    "Detalle: conexión TCP fallida (puerto 5432 bloqueado o servidor inaccesible)."
                ) from e
        try:
            if self.pool_enabled:
                self.pool = psycopg2.pool.ThreadedConnectionPool(self.pool_minconn, self.pool_maxconn, **self.conn_params)
                self.conn = self.pool.getconn()
            else:
                self.conn = psycopg2.connect(**self.conn_params)
        except Exception as e:
            msg = str(e or "").lower()
            if "timeout expired" in msg or "could not connect" in msg or "connection to server" in msg:
                self.last_error = e
                raise RuntimeError(
                    "No se pudo conectar a PostgreSQL.\n"
                    f"Destino: {host}:{port}  DB: {self.conn_params.get('dbname','')}  Usuario: {self.conn_params.get('user','')}\n"
                    f"Detalle: {type(e).__name__}: {e}"
                ) from e
            if isinstance(e, UnicodeDecodeError) and isinstance(getattr(e, "object", None), (bytes, bytearray)):
                try:
                    decoded = bytes(e.object).decode("latin1", errors="replace")
                    self.last_error = RuntimeError(decoded)
                except Exception:
                    self.last_error = e
            else:
                self.last_error = e
            try:
                if "does not exist" not in msg and "no existe" not in msg:
                    raise e
                maint = dict(self.conn_params)
                maint["dbname"] = os.environ.get("REVIEWDATA_DB_MAINTENANCE_DB", "postgres").strip()
                conn = psycopg2.connect(**maint)
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.conn_params["dbname"],))
                    exists = cur.fetchone() is not None
                    if not exists:
                        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.conn_params["dbname"])))
                conn.close()
                if self.pool_enabled:
                    self.pool = psycopg2.pool.ThreadedConnectionPool(self.pool_minconn, self.pool_maxconn, **self.conn_params)
                    self.conn = self.pool.getconn()
                else:
                    self.conn = psycopg2.connect(**self.conn_params)
            except Exception as e2:
                if isinstance(e2, UnicodeDecodeError) and isinstance(getattr(e2, "object", None), (bytes, bytearray)):
                    try:
                        decoded = bytes(e2.object).decode("latin1", errors="replace")
                        self.last_error = RuntimeError(decoded)
                    except Exception:
                        self.last_error = e2
                else:
                    self.last_error = e2
                self.conn = None
                host = str(self.conn_params.get("host") or "")
                port = str(self.conn_params.get("port") or "")
                user = str(self.conn_params.get("user") or "")
                dbname = str(self.conn_params.get("dbname") or "")
                detail = self.last_error
                raise RuntimeError(
                    "No se pudo conectar a PostgreSQL.\n"
                    f"Destino: {host}:{port}  DB: {dbname}  Usuario: {user}\n"
                    "Configura las variables de entorno:\n"
                    "- REVIEWDATA_DB_HOST\n"
                    "- REVIEWDATA_DB_PORT\n"
                    "- REVIEWDATA_DB_USER\n"
                    "- REVIEWDATA_DB_PASSWORD\n"
                    "- REVIEWDATA_DB_NAME\n"
                    f"Detalle: {type(detail).__name__}: {detail}"
                ) from self.last_error

    def _pool_open(self) -> bool:
        return bool(getattr(self, "pool", None))

    def _get_conn_for_op(self):
        self._ensure_connection()
        if getattr(self, "_schema_mode", False):
            return self.conn, lambda: None
        if self._pool_open():
            conn = self.pool.getconn()

            def _release():
                try:
                    self.pool.putconn(conn)
                except Exception:
                    pass

            return conn, _release

        return self.conn, lambda: None

    def _conn_open(self) -> bool:
        c = getattr(self, "conn", None)
        if not c:
            return False
        try:
            return int(getattr(c, "closed", 1) or 1) == 0
        except Exception:
            return False

    def _ensure_connection(self):
        if self._pool_open():
            return
        if not self._conn_open():
            self.connect()

    def ensure_schema(self):
        if not self.conn:
            raise RuntimeError("PostgreSQL no está conectado.")
        try:
            self._schema_mode = True
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_lock(790447001)")
            except Exception:
                pass
            core_schema = """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS suggested_required_columns (
                id SERIAL PRIMARY KEY,
                column_name TEXT UNIQUE NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                rule_id TEXT PRIMARY KEY,
                recommendation TEXT NOT NULL,
                action_type TEXT,
                source TEXT NOT NULL DEFAULT 'static',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                records INTEGER NOT NULL,
                folios INTEGER NOT NULL,
                status TEXT NOT NULL,
                user_email TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                columns_json TEXT NOT NULL,
                file_bytes BYTEA,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_datasets_created_at ON datasets (created_at DESC);

            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                user_email TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                total_records INTEGER NOT NULL,
                inconsistencies INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_dataset_created_at ON runs (dataset_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                row_index INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_findings_created_at ON findings (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_findings_run_created_at ON findings (run_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_findings_dataset_created_at ON findings (dataset_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings (severity);

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                format TEXT NOT NULL,
                status TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports (created_at DESC);

            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                user_email TEXT NOT NULL,
                module TEXT NOT NULL,
                action TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            ok = self.execute_script(core_schema)
            if not ok:
                raise RuntimeError("No se pudo crear el esquema base en PostgreSQL.")
            try:
                has_role = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'role' LIMIT 1"
                )
                if not has_role:
                    self.execute_query("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            except Exception:
                pass
            try:
                has_file_bytes = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'file_bytes' LIMIT 1"
                )
                if not has_file_bytes:
                    self.execute_query("ALTER TABLE datasets ADD COLUMN file_bytes BYTEA")
            except Exception:
                pass
            try:
                has_profile = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'profile_json' LIMIT 1"
                )
                if not has_profile:
                    self.execute_query("ALTER TABLE datasets ADD COLUMN profile_json TEXT")
            except Exception:
                pass
            try:
                has_contract_ok = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'contract_ok' LIMIT 1"
                )
                if not has_contract_ok:
                    self.execute_query("ALTER TABLE datasets ADD COLUMN contract_ok BOOLEAN")
            except Exception:
                pass
            try:
                has_contract_issues = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'contract_issues_json' LIMIT 1"
                )
                if not has_contract_issues:
                    self.execute_query("ALTER TABLE datasets ADD COLUMN contract_issues_json TEXT")
            except Exception:
                pass
            try:
                has_quality = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'datasets' AND column_name = 'quality_score' LIMIT 1"
                )
                if not has_quality:
                    self.execute_query("ALTER TABLE datasets ADD COLUMN quality_score INTEGER")
            except Exception:
                pass
            try:
                has_run_quality = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'runs' AND column_name = 'quality_score' LIMIT 1"
                )
                if not has_run_quality:
                    self.execute_query("ALTER TABLE runs ADD COLUMN quality_score INTEGER")
            except Exception:
                pass
            try:
                has_rules_applied = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'runs' AND column_name = 'rules_applied_json' LIMIT 1"
                )
                if not has_rules_applied:
                    self.execute_query("ALTER TABLE runs ADD COLUMN rules_applied_json TEXT")
            except Exception:
                pass
            try:
                has_rules_passed = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'runs' AND column_name = 'rules_passed_json' LIMIT 1"
                )
                if not has_rules_passed:
                    self.execute_query("ALTER TABLE runs ADD COLUMN rules_passed_json TEXT")
            except Exception:
                pass
            try:
                has_rules_failed = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'runs' AND column_name = 'rules_failed_json' LIMIT 1"
                )
                if not has_rules_failed:
                    self.execute_query("ALTER TABLE runs ADD COLUMN rules_failed_json TEXT")
            except Exception:
                pass
            try:
                has_error_type = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'findings' AND column_name = 'error_type' LIMIT 1"
                )
                if not has_error_type:
                    self.execute_query("ALTER TABLE findings ADD COLUMN error_type TEXT")
            except Exception:
                pass
            try:
                has_expected = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'findings' AND column_name = 'expected' LIMIT 1"
                )
                if not has_expected:
                    self.execute_query("ALTER TABLE findings ADD COLUMN expected TEXT")
            except Exception:
                pass
            try:
                has_recommendation = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'findings' AND column_name = 'recommendation' LIMIT 1"
                )
                if not has_recommendation:
                    self.execute_query("ALTER TABLE findings ADD COLUMN recommendation TEXT")
            except Exception:
                pass

            try:
                has_business_impact = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'findings' AND column_name = 'business_impact' LIMIT 1"
                )
                if not has_business_impact:
                    self.execute_query("ALTER TABLE findings ADD COLUMN business_impact TEXT")
            except Exception:
                pass

            try:
                has_rule_params = self.fetch_all(
                    "SELECT 1 AS x FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'rules' AND column_name = 'parameters_json' LIMIT 1"
                )
                if not has_rule_params:
                    self.execute_query("ALTER TABLE rules ADD COLUMN parameters_json TEXT")
            except Exception:
                pass

            ai_schema = """
            CREATE TABLE IF NOT EXISTS ai_insights (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_ai_insights_run ON ai_insights (run_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                rule_id TEXT,
                column_name TEXT,
                problem TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                priority TEXT NOT NULL,
                business_impact TEXT,
                can_auto_fix BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_ai_recs_run ON ai_recommendations (run_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS dataset_drift (
                id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                current_run_id TEXT NOT NULL,
                previous_run_id TEXT NOT NULL,
                drift_type TEXT NOT NULL,
                field TEXT,
                previous_value TEXT,
                current_value TEXT,
                difference TEXT,
                severity TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_drift_current_run ON dataset_drift (current_run_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_drift_dataset ON dataset_drift (dataset_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS suggested_expectations (
                id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                column_name TEXT NOT NULL,
                expectation_type TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'suggested',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_suggested_expectations_dataset ON suggested_expectations (dataset_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS auto_fix_suggestions (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                finding_id TEXT,
                column_name TEXT NOT NULL,
                original_value TEXT NOT NULL,
                fixed_value TEXT NOT NULL,
                fix_type TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
                status TEXT NOT NULL DEFAULT 'suggested',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_auto_fix_run ON auto_fix_suggestions (run_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS dataset_health (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                score INTEGER NOT NULL,
                grade TEXT NOT NULL,
                explanation TEXT NOT NULL,
                critical_count INTEGER NOT NULL,
                high_count INTEGER NOT NULL,
                medium_count INTEGER NOT NULL,
                low_count INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_dataset_health_run ON dataset_health (run_id, created_at DESC);
            """
            try:
                self.execute_script(ai_schema)
            except Exception:
                pass

            default_email = os.environ.get("REVIEWDATA_DEFAULT_EMAIL", "admin@reviewdata.local").strip()
            default_password = os.environ.get("REVIEWDATA_DEFAULT_PASSWORD", "admin123")
            seed_user_email = os.environ.get("REVIEWDATA_SEED_USER_EMAIL", "user@reviewdata.local").strip()
            seed_user_password = os.environ.get("REVIEWDATA_SEED_USER_PASSWORD", "user123")

            rows = self.fetch_all("SELECT COUNT(*) AS n FROM users")
            if rows and int(rows[0].get("n", 0)) == 0:
                from services.auth_service import _sha256

                self.execute_query(
                    """
                    INSERT INTO users (id, email, password_hash, role, active)
                    VALUES (%s, %s, %s, 'admin', TRUE)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (str(uuid.uuid4()), default_email, _sha256(default_password)),
                )
            self.execute_query("UPDATE users SET role = 'admin' WHERE lower(email) = lower(%s)", (default_email,))
            try:
                from services.auth_service import _sha256

                self.execute_query(
                    """
                    INSERT INTO users (id, email, password_hash, role, active)
                    VALUES (%s, %s, %s, 'user', TRUE)
                    ON CONFLICT (email) DO NOTHING
                    """,
                    (str(uuid.uuid4()), seed_user_email, _sha256(seed_user_password)),
                )
            except Exception:
                pass

            suggested = [
                "Folio_reporte",
                "Numero_remision",
                "Numero_operador",
                "Nombre_operador",
                "Fecha_reporte",
                "Descripcion",
                "OC",
                "Origen_destino",
                "Ruta_autorizada",
                "Remitente_cliente",
            ]
            rows = self.fetch_all("SELECT COUNT(*) AS n FROM suggested_required_columns")
            if rows and int(rows[0].get("n", 0)) == 0:
                for c in suggested:
                    self.execute_query(
                        """
                        INSERT INTO suggested_required_columns (column_name, active)
                        VALUES (%s, TRUE)
                        ON CONFLICT (column_name) DO NOTHING
                        """,
                        (c,),
                    )

            legacy_schema = """
            CREATE TABLE IF NOT EXISTS validaciones_severidades (
                id_severidad SERIAL PRIMARY KEY,
                nombre VARCHAR(50) NOT NULL UNIQUE,
                descripcion TEXT,
                nivel INTEGER NOT NULL,
                activo BOOLEAN NOT NULL DEFAULT TRUE,
                fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS gestion_datos_usuarios (
                id_usuario SERIAL PRIMARY KEY,
                nombre VARCHAR(120),
                email VARCHAR(200) NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol VARCHAR(50) NOT NULL DEFAULT 'user',
                activo BOOLEAN NOT NULL DEFAULT TRUE,
                fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS informacion_bitacora_usuarios (
                id_bitacora SERIAL PRIMARY KEY,
                id_usuario INTEGER,
                accion VARCHAR(200) NOT NULL,
                modulo VARCHAR(200) NOT NULL,
                descripcion TEXT,
                fecha_accion TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
            try:
                self.execute_script(legacy_schema)
            except Exception:
                pass
            legacy_schema2 = """
            CREATE TABLE IF NOT EXISTS validaciones_reglas (
                id_regla SERIAL PRIMARY KEY,
                nombre VARCHAR(120) NOT NULL,
                descripcion TEXT,
                expresion TEXT,
                id_severidad INTEGER,
                activa BOOLEAN NOT NULL DEFAULT TRUE,
                fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_validaciones_reglas_sev ON validaciones_reglas (id_severidad);

            CREATE TABLE IF NOT EXISTS gestion_datasets_cargados (
                id_dataset SERIAL PRIMARY KEY,
                nombre VARCHAR(255) NOT NULL,
                tipo_archivo VARCHAR(20) NOT NULL,
                fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
                tiempo_carga_segundos INTEGER,
                total_registros INTEGER NOT NULL DEFAULT 0,
                estado VARCHAR(50) NOT NULL DEFAULT 'Cargado',
                id_usuario INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_gestion_datasets_usuario ON gestion_datasets_cargados (id_usuario);

            CREATE TABLE IF NOT EXISTS procesamiento_ejecuciones (
                id_ejecucion SERIAL PRIMARY KEY,
                id_dataset INTEGER NOT NULL,
                fecha_inicio TIMESTAMPTZ NOT NULL DEFAULT now(),
                fecha_fin TIMESTAMPTZ,
                estado VARCHAR(50) NOT NULL DEFAULT 'Completado',
                total_inconsistencias INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_proc_ejecuciones_dataset ON procesamiento_ejecuciones (id_dataset);

            CREATE TABLE IF NOT EXISTS procesamiento_hallazgos (
                id_hallazgo SERIAL PRIMARY KEY,
                id_ejecucion INTEGER NOT NULL,
                id_regla INTEGER,
                campo_afectado VARCHAR(255),
                valor_detectado TEXT,
                descripcion TEXT,
                id_severidad INTEGER,
                fecha_deteccion TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_proc_hallazgos_ejec ON procesamiento_hallazgos (id_ejecucion);
            CREATE INDEX IF NOT EXISTS idx_proc_hallazgos_regla ON procesamiento_hallazgos (id_regla);

            CREATE TABLE IF NOT EXISTS reportes_estadisticas (
                id_estadistica SERIAL PRIMARY KEY,
                id_ejecucion INTEGER NOT NULL,
                porcentaje_error DECIMAL(5,2) NOT NULL DEFAULT 0,
                total_validos INTEGER NOT NULL DEFAULT 0,
                total_invalidos INTEGER NOT NULL DEFAULT 0,
                fecha_calculo TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_reportes_estad_ejec ON reportes_estadisticas (id_ejecucion);

            CREATE TABLE IF NOT EXISTS reportes_recomendaciones (
                id_recomendacion SERIAL PRIMARY KEY,
                id_regla INTEGER,
                descripcion TEXT NOT NULL,
                tipo_accion VARCHAR(120),
                activo BOOLEAN NOT NULL DEFAULT TRUE,
                fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_reportes_recom_regla ON reportes_recomendaciones (id_regla);

            CREATE TABLE IF NOT EXISTS reportes_reportes_generados (
                id_reporte SERIAL PRIMARY KEY,
                id_ejecucion INTEGER,
                id_usuario INTEGER,
                tipo_reporte VARCHAR(120) NOT NULL,
                formato VARCHAR(50) NOT NULL,
                nombre_archivo VARCHAR(255),
                ruta_archivo TEXT,
                fecha_generacion TIMESTAMPTZ NOT NULL DEFAULT now(),
                tiempo_generacion_segundos INTEGER,
                estado VARCHAR(50) NOT NULL DEFAULT 'Completado'
            );
            CREATE INDEX IF NOT EXISTS idx_reportes_gen_ejec ON reportes_reportes_generados (id_ejecucion);

            CREATE TABLE IF NOT EXISTS reportes_detalle_reportes_generados (
                id_detalle_reporte SERIAL PRIMARY KEY,
                id_reporte INTEGER NOT NULL,
                id_hallazgo INTEGER,
                id_estadistica INTEGER,
                observaciones TEXT,
                fecha_accion TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_reportes_det_reporte ON reportes_detalle_reportes_generados (id_reporte);
            """
            try:
                self.execute_script(legacy_schema2)
            except Exception:
                pass

            rows = self.fetch_all("SELECT COUNT(*) AS n FROM validaciones_severidades")
            if rows and int(rows[0].get("n", 0)) == 0:
                seeds = [
                    ("Cr\u00edtica", "Error cr\u00edtico", 4),
                    ("Alta", "Error alto", 3),
                    ("Media", "Error medio", 2),
                    ("Baja", "Error bajo", 1),
                ]
                for nombre, descripcion, nivel in seeds:
                    self.execute_query(
                        """
                        INSERT INTO validaciones_severidades (nombre, descripcion, nivel, activo)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (nombre) DO NOTHING
                        """,
                        (nombre, descripcion, int(nivel)),
                    )
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(790447001)")
            except Exception:
                pass
        except Exception as e:
            self.last_error = e
            raise
        finally:
            self._schema_mode = False

    def execute_script(self, script: str) -> bool:
        q = (script or "").strip()
        if not q:
            return True
        for attempt in range(2):
            try:
                conn, release = self._get_conn_for_op()
                try:
                    with conn.cursor() as cur:
                        cur.execute(q)
                    conn.commit()
                finally:
                    release()
                return True
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
                self.last_error = e
                try:
                    if getattr(self, "conn", None):
                        self.conn.close()
                except Exception:
                    pass
                self.conn = None
                try:
                    if getattr(self, "pool", None):
                        self.pool.closeall()
                except Exception:
                    pass
                self.pool = None
                if attempt == 0:
                    continue
                print(f"Fallo la consulta: {e}")
                return False
            except psycopg2.Error as e:
                self.last_error = e
                print(f"Fallo la consulta: {e}")
                try:
                    if getattr(self, "conn", None):
                        self.conn.rollback()
                except Exception:
                    pass
                return False

    def execute_query(self, query, params=None):
        for attempt in range(2):
            try:
                conn, release = self._get_conn_for_op()
                try:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                    conn.commit()
                finally:
                    release()
                return True
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
                self.last_error = e
                try:
                    if getattr(self, "conn", None):
                        self.conn.close()
                except Exception:
                    pass
                self.conn = None
                try:
                    if getattr(self, "pool", None):
                        self.pool.closeall()
                except Exception:
                    pass
                self.pool = None
                msg = str(e or "").lower()
                if attempt == 0 and ("timeout expired" in msg or "could not connect" in msg or "connection to server" in msg):
                    return False
                if attempt == 0:
                    continue
                print(f"Fallo la consulta: {e}")
                return False
            except psycopg2.Error as e:
                self.last_error = e
                print(f"Fallo la consulta: {e}")
                try:
                    if getattr(self, "conn", None):
                        self.conn.rollback()
                except Exception:
                    pass
                return False

    def fetch_all(self, query, params=None):
        for attempt in range(2):
            try:
                conn, release = self._get_conn_for_op()
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute(query, params)
                        return [dict(row) for row in cur.fetchall()]
                finally:
                    release()
            except (psycopg2.InterfaceError, psycopg2.OperationalError) as e:
                self.last_error = e
                try:
                    if getattr(self, "conn", None):
                        self.conn.close()
                except Exception:
                    pass
                self.conn = None
                try:
                    if getattr(self, "pool", None):
                        self.pool.closeall()
                except Exception:
                    pass
                self.pool = None
                msg = str(e or "").lower()
                if attempt == 0 and ("timeout expired" in msg or "could not connect" in msg or "connection to server" in msg):
                    return []
                if attempt == 0:
                    continue
                print(f"Fallo la obtención de datos: {e}")
                return []
            except psycopg2.Error as e:
                self.last_error = e
                print(f"Fallo la obtención de datos: {e}")
                return []

    def close(self):
        try:
            if getattr(self, "pool", None):
                try:
                    if getattr(self, "conn", None):
                        self.pool.putconn(self.conn)
                except Exception:
                    pass
                self.pool.closeall()
        except Exception:
            pass
        self.pool = None
        try:
            if getattr(self, "conn", None):
                self.conn.close()
        except Exception:
            pass
        self.conn = None
