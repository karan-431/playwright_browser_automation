from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from fastapi.templating import Jinja2Templates

from automation import run_test

app = FastAPI()

templates = Jinja2Templates(directory="templates")

app.mount("/screenshots", StaticFiles(directory="screenshots"), name="screenshots")
app.mount("/reports", StaticFiles(directory="reports"), name="reports")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.post("/run")
def run(url: str = Form(...), prompt: str = Form(...)):

    report = run_test(url, prompt)

    return {
        "message": "Automation completed",
        "report": report
    }