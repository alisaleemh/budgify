from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from webapp import config_manager
from webapp.runner import Runner

app = FastAPI(title="Budgify UI")
templates = Jinja2Templates(directory="webapp/templates")

runner = Runner()
config_manager.ensure_config_file()


@app.get("/")
async def index(request: Request, message: str | None = None, error: str | None = None):
    config = config_manager.load_config()
    categories = config.get("categories", {})
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories,
            "message": message,
            "error": error,
            "run_status": runner.status_payload(),
            "statements_path": "/statements",
            "config_path": "/app/config.yaml",
        },
    )


@app.post("/categories/add")
async def add_category(name: str = Form(...)):
    clean_name = name.strip()
    if not clean_name:
        return RedirectResponse("/?error=Category%20name%20is%20required", status_code=303)
    config = config_manager.load_config()
    categories = config.get("categories", {})
    if clean_name in categories:
        return RedirectResponse("/?error=Category%20already%20exists", status_code=303)
    config_manager.add_category(clean_name)
    return RedirectResponse("/?message=Category%20added", status_code=303)


@app.post("/categories/delete")
async def delete_category(name: str = Form(...)):
    config_manager.delete_category(name)
    return RedirectResponse("/?message=Category%20deleted", status_code=303)


@app.post("/categories/rename")
async def rename_category(old_name: str = Form(...), new_name: str = Form(...)):
    old = old_name.strip()
    new = new_name.strip()
    if not new:
        return RedirectResponse("/?error=New%20name%20is%20required", status_code=303)
    config = config_manager.load_config()
    categories = config.get("categories", {})
    if old not in categories:
        return RedirectResponse("/?error=Category%20not%20found", status_code=303)
    if new in categories:
        return RedirectResponse("/?error=Category%20name%20already%20in%20use", status_code=303)
    config_manager.rename_category(old, new)
    return RedirectResponse("/?message=Category%20renamed", status_code=303)


@app.post("/run")
async def run_budgify():
    if runner.is_running:
        return RedirectResponse("/?error=Budgify%20is%20already%20running", status_code=303)
    try:
        runner.run_budgify()
        return RedirectResponse("/?message=Budgify%20completed", status_code=303)
    except RuntimeError as exc:  # pragma: no cover - defensive guard
        return RedirectResponse(f"/?error={str(exc)}", status_code=303)


@app.post("/reload")
async def reload_config():
    config_manager.ensure_config_file()
    return RedirectResponse("/?message=Config%20reloaded", status_code=303)
