from app.models.db import get_connection

class ModelEngineRepository:
    
    @staticmethod
    def get_models_list(page: int, limit: int):
        offset = (page - 1) * limit
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_models ORDER BY is_default DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            total = conn.execute("SELECT COUNT(1) as cnt FROM ai_models").fetchone()["cnt"]
        return [dict(row) for row in rows], total

    @staticmethod
    def get_model_by_id(model_id: int):
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ai_models WHERE id = ?", (model_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def create_model(name: str, model_name: str, api_key: str, base_url: str) -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO ai_models (name, model_name, api_key, base_url) VALUES (?, ?, ?, ?)",
                    (name, model_name, api_key, base_url)
                )
            return True
        except Exception:
            return False

    @staticmethod
    def update_model(model_id: int, name: str, model_name: str, api_key: str, base_url: str) -> bool:
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE ai_models SET name=?, model_name=?, api_key=?, base_url=? WHERE id=?",
                    (name, model_name, api_key, base_url, model_id)
                )
            return True
        except Exception:
            return False

    @staticmethod
    def delete_model(model_id: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("DELETE FROM ai_models WHERE id=?", (model_id,))
            return True
        except Exception:
            return False

    @staticmethod
    def set_default(model_id: int) -> bool:
        try:
            with get_connection() as conn:
                conn.execute("UPDATE ai_models SET is_default = 0")
                conn.execute("UPDATE ai_models SET is_default = 1 WHERE id=?", (model_id,))
            return True
        except Exception:
            return False

    @staticmethod
    def add_tokens(model_id: int, tokens: int):
        try:
            with get_connection() as conn:
                conn.execute("UPDATE ai_models SET total_tokens = total_tokens + ? WHERE id=?", (tokens, model_id))
        except Exception:
            pass
