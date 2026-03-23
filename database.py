
import psycopg2
import psycopg2.extras

class Database:
    """Manages the connection and queries to the PostgreSQL database."""
    def __init__(self):
        # IMPORTANTE: Reemplaza esto con tus credenciales reales de PostgreSQL.
        self.conn_params = {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "1234",
            "dbname": "tu_db"
        }
        self.conn = None
        self.connect()

    def connect(self):
        """Establishes the connection to the database."""
        try:
            # Reemplaza estas credenciales con tus datos reales antes de ejecutar
            self.conn_params = {
                "host": "localhost",
                "port": "5432",
                "user": "postgres",
                "password": "tu_password",
                "dbname": "tu_db"
            }
            # Solo intentar conectar si no son los valores por defecto
            if self.conn_params["password"] != "tu_password":
                self.conn = psycopg2.connect(**self.conn_params)
            else:
                print("Aviso: Credenciales de base de datos no configuradas en database.py")
                self.conn = None
        except Exception as e:
            print(f"Error al conectar a la base de datos: {e}")
            self.conn = None

    def execute_query(self, query, params=None):
        """Executes a query (INSERT, UPDATE, DELETE) and commits."""
        if not self.conn: return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
            self.conn.commit()
            return True
        except psycopg2.Error as e:
            print(f"Fallo la consulta: {e}")
            self.conn.rollback()
            return False

    def fetch_all(self, query, params=None):
        """Executes a SELECT query and returns all results as dicts."""
        if not self.conn: return []
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Fallo la obtención de datos: {e}")
            return []

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
