from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from infrastructure.database import Database
from services.data_service import DataService

app = FastAPI(title="ReviewData Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.RLock()
_db: Database | None = None
_svc: DataService | None = None


def _get_service() -> DataService:
    global _db, _svc
    if _svc is not None and _db is not None:
        return _svc
    with _lock:
        if _svc is not None and _db is not None:
            return _svc
        try:
            _db = Database()
            _svc = DataService(_db)
            return _svc
        except Exception as e:
            raise HTTPException(status_code=503, detail=str(e))


class LoginRequest(BaseModel):
    email: str
    password: str


class ValidateRequest(BaseModel):
    rule_ids: list[str]
    mapping: dict = {}

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "user"
    active: bool = True


class UpdateUserRequest(BaseModel):
    role: str | None = None
    active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class CreateRuleRequest(BaseModel):
    rule_id: str
    name: str
    description: str
    rule_type: str
    severity: str
    active: bool = True


class ToggleRuleRequest(BaseModel):
    active: bool

class AcceptExpectationsRequest(BaseModel):
    expectation_ids: list[str]

class AiQueryRequest(BaseModel):
    question: str
    dataset_id: str | None = None
    run_id: str | None = None


class ApplyAutoFixRequest(BaseModel):
    suggestion_ids: list[str] | None = None


def _require_auth(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Falta Authorization.")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Authorization inválido.")
    token = parts[1].strip()
    svc = _get_service()
    ok = svc.set_session(token)
    if not ok:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")
    return token


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    svc = _get_service()
    session = svc.authenticate(payload.email, payload.password)
    if not session:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    return session


@app.get("/api/auth/me")
def me(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_current_user() or {}


@app.get("/api/dashboard/stats")
def dashboard_stats(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_dashboard_stats()


@app.get("/api/rules")
def list_rules(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_rules()


@app.get("/api/datasets")
def list_datasets(offset: int = 0, limit: int = 200, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    svc = _get_service()
    return svc.get_datasets_page(offset=offset, limit=limit)


@app.get("/api/datasets/{dataset_id}/columns")
def dataset_columns(dataset_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_dataset_columns(dataset_id)


@app.get("/api/datasets/{dataset_id}/row-preview")
def dataset_row_preview(dataset_id: str, row_index: int, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    row = svc.get_dataset_row_preview(dataset_id, int(row_index))
    if not row:
        raise HTTPException(status_code=404, detail="Fila no disponible.")
    return row


@app.get("/api/datasets/{dataset_id}/preview")
def dataset_preview(dataset_id: str, offset: int = 0, limit: int = 20, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_dataset_preview(dataset_id, offset=offset, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_dataset_profile(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/datasets/upload")
async def upload_dataset(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    schema_json_str: str = Form(default="{}"),
):
    _require_auth(authorization)
    name = (file.filename or "").strip() or "dataset.csv"
    if not name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se aceptan CSV.")
    try:
        schema = json.loads(schema_json_str or "{}")
        if not isinstance(schema, dict):
            schema = {}
    except Exception:
        schema = {}

    base_dir = (os.environ.get("REVIEWDATA_DATA_DIR") or "").strip()
    if not base_dir:
        base_dir = str((Path.cwd() / "_web_storage").resolve())
        os.environ["REVIEWDATA_DATA_DIR"] = base_dir
    tmp_dir = Path(base_dir) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="upload_", suffix=".csv", dir=str(tmp_dir))
        os.close(fd)
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content or b"")
        svc = _get_service()
        ds = svc.import_dataset(tmp_path, schema, original_filename=name)
        return ds
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/api/runs")
def list_runs(dataset_id: str | None = None, offset: int = 0, limit: int = 200, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    svc = _get_service()
    return svc.get_runs_page(dataset_id=dataset_id, offset=offset, limit=limit)


@app.post("/api/runs/{dataset_id}/validate")
def validate(dataset_id: str, payload: ValidateRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.run_validation(dataset_id, payload.rule_ids or [], payload.mapping or {})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/findings")
def list_findings(
    dataset_id: str | None = None,
    run_id: str | None = None,
    offset: int = 0,
    limit: int = 200,
    authorization: str | None = Header(default=None),
):
    _require_auth(authorization)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    svc = _get_service()
    return svc.get_findings_page(dataset_id=dataset_id, run_id=run_id, offset=offset, limit=limit)


@app.get("/api/stats/severity")
def stats_severity(dataset_id: str | None = None, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_severity_counts(dataset_id=dataset_id)


@app.get("/api/stats/overview")
def stats_overview(dataset_id: str | None = None, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_stats_overview(dataset_id=dataset_id)


@app.get("/api/stats/trends")
def stats_trends(days: int = 7, dataset_id: str | None = None, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    return svc.get_trends(days=int(days or 7), dataset_id=dataset_id)


@app.get("/api/insights")
def insights(run_id: str | None = None, days: int = 7, dataset_id: str | None = None, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    _ = days
    rid = (run_id or "").strip()
    if not rid:
        try:
            page = svc.get_runs_page(dataset_id=dataset_id, offset=0, limit=1)
            items = page.get("items") if isinstance(page, dict) else []
            if isinstance(items, list) and items:
                rid = str((items[0] or {}).get("id") or "").strip()
        except Exception:
            rid = ""
    if not rid:
        return []
    return svc.get_ai_insights(rid)


@app.get("/api/recommendations")
def recommendations(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_recommendations(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/insights")
def ai_insights(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_ai_insights(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/recommendations")
def ai_recommendations(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_ai_recommendations(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/drift")
def ai_drift(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_dataset_drift(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/expectations")
def ai_expectations(dataset_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_suggested_expectations(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/expectations/{dataset_id}/accept")
def ai_accept_expectations(dataset_id: str, payload: AcceptExpectationsRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.accept_suggested_expectations(dataset_id, payload.expectation_ids or [])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/query")
def ai_query(payload: AiQueryRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.answer_nl_query(payload.question, dataset_id=payload.dataset_id, run_id=payload.run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/autofix")
def ai_autofix(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_auto_fix_suggestions(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/autofix/{run_id}/apply")
def ai_autofix_apply(run_id: str, payload: ApplyAutoFixRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        out_path = svc.build_auto_fixed_csv(run_id, payload.suggestion_ids or None)
        return FileResponse(out_path, media_type="text/csv", filename=f"ReviewData_Autofix_{run_id[:8]}.csv")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/findings/grouped")
def ai_grouped_findings(run_id: str, limit: int = 200, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_grouped_findings(run_id, limit=int(limit or 200))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/findings/{finding_id}/explain")
def ai_explain_finding(finding_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.explain_finding(finding_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/findings/{finding_id}/create-rule")
def ai_create_rule_from_finding(finding_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.create_rule_from_finding(finding_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/reports")
def list_reports(offset: int = 0, limit: int = 200, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    svc = _get_service()
    return svc.get_reports_page(offset=offset, limit=limit)


@app.get("/api/reports/{run_id}/pdf")
def download_report_pdf(run_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    base_dir = (os.environ.get("REVIEWDATA_DATA_DIR") or "").strip()
    if not base_dir:
        base_dir = str((Path.cwd() / "_web_storage").resolve())
        os.environ["REVIEWDATA_DATA_DIR"] = base_dir
    out_dir = Path(base_dir) / "tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, out_path = tempfile.mkstemp(prefix=f"report_{run_id[:8]}_", suffix=".pdf", dir=str(out_dir))
    os.close(fd)
    try:
        svc = _get_service()
        svc.export_run_pdf(run_id, out_path)
        return FileResponse(out_path, media_type="application/pdf", filename=f"ReviewData_{run_id[:8]}.pdf")
    except Exception as e:
        try:
            os.remove(out_path)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/admin/summary")
def admin_summary(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_admin_summary()
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/admin/activity")
def admin_activity(limit: int = 200, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.get_activity(limit=int(limit))
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.get("/api/admin/users")
def admin_list_users(authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.list_users()
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/admin/users")
def admin_create_user(payload: CreateUserRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        return svc.create_user(payload.email, payload.password, role=payload.role, active=bool(payload.active))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: UpdateUserRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        ok = svc.update_user(user_id, role=payload.role, active=payload.active)
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/users/{user_id}/password")
def admin_reset_password(user_id: str, payload: ResetPasswordRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        ok = svc.reset_user_password(user_id, payload.new_password)
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        ok = svc.delete_user(user_id)
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/rules")
def admin_create_rule(payload: CreateRuleRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        ok = svc.create_rule(payload.rule_id, payload.name, payload.description, payload.rule_type, payload.severity, bool(payload.active))
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/admin/rules/{rule_id}")
def admin_toggle_rule(rule_id: str, payload: ToggleRuleRequest, authorization: str | None = Header(default=None)):
    _require_auth(authorization)
    svc = _get_service()
    try:
        ok = svc.set_rule_active(rule_id, bool(payload.active))
        return {"ok": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
