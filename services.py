from interfaces import IDataService
from database import Database

class DataService(IDataService):
    """Concrete implementation that uses a real database connection."""
    def __init__(self, db: Database):
        self._db = db

    def get_all_datasets(self) -> list:
        if not self._db.conn:
            return [
                {"id": "1", "name": "Ejemplo Offline", "type": "CSV", "records": 100, "date": "09-03-2026", "status": "Offline"}
            ]
        # Ajustado a tus columnas reales: nombre_archivo, formato, total_registros, fecha_carga
        query = "SELECT id, nombre_archivo as name, formato as type, total_registros as records, fecha_carga as date FROM datasets ORDER BY fecha_carga DESC;"
        return self._db.fetch_all(query)

    def add_dataset(self, name: str, file_type: str, records: int) -> dict:
        if not self._db.conn:
            return {"id": "MOCK", "name": name, "type": file_type, "records": records, "date": "HOY", "status": "Mock"}
        
        # Ajustado a tus columnas reales. He añadido usuario_id con valor 1 por defecto.
        query = """
        INSERT INTO datasets (usuario_id, nombre_archivo, formato, total_registros, fecha_carga)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id, nombre_archivo as name, formato as type, total_registros as records, fecha_carga as date;
        """
        params = (1, name, file_type.upper(), records)
        result = self._db.fetch_all(query, params)
        if result:
            self._db.conn.commit()
            return result[0]
        return None
