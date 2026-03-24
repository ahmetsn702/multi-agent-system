"""
tools/project_templates.py
ProjectTemplates: Hazir baslangic sablonlari.
Coder her seferinde sifirdan baslamak yerine
sablonu alir, ustune ekler.
"""
from pathlib import Path

TEMPLATES = {
    "flask_api": {
        "description": "Flask REST API sablonu",
        "files": {
            "src/app.py": '''from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route("/health")
def health():
    """Saglik kontrolu endpoint'i."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
''',
            "src/models.py": '''# Veritabani modelleri buraya
''',
            "requirements.txt": "flask\nflask-cors\n",
            "tests/test_app.py": '''import pytest
from src.app import app


@pytest.fixture
def client():
    """Test istemcisi."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    """Saglik endpoint testi."""
    response = client.get("/health")
    assert response.status_code == 200
''',
        }
    },
    "tkinter_gui": {
        "description": "Tkinter GUI sablonu",
        "files": {
            "src/main.py": '''import tkinter as tk
from tkinter import ttk, messagebox


class App(tk.Tk):
    """Ana uygulama penceresi."""

    def __init__(self):
        super().__init__()
        self.title("Uygulama")
        self.geometry("800x600")
        self._build_ui()

    def _build_ui(self):
        """UI bilesenleri olustur."""
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Merhaba!").pack()


if __name__ == "__main__":
    app = App()
    app.mainloop()
''',
        }
    },
    "cli_tool": {
        "description": "Click CLI arac sablonu",
        "files": {
            "src/cli.py": '''import click


@click.group()
def cli():
    """CLI Araci"""
    pass


@cli.command()
@click.argument("name")
def greet(name):
    """Kullaniciyi selamla."""
    click.echo(f"Merhaba, {name}!")


if __name__ == "__main__":
    cli()
''',
            "requirements.txt": "click\n",
        }
    },
    "sqlite_app": {
        "description": "SQLite veritabani sablonu",
        "files": {
            "src/database.py": '''import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data.db"


def get_conn():
    """Veritabani baglantisi dondur."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Veritabanini olustur."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


if __name__ == "__main__":
    init_db()
    print("Veritabani hazir.")
''',
        }
    },
    "fastapi_api": {
        "description": "FastAPI REST API sablonu",
        "files": {
            "src/app.py": '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Saglik kontrolu endpoint'i."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=True)
''',
            "src/models.py": '''# Veritabani modelleri buraya
''',
            "requirements.txt": "fastapi\nuvicorn\n",
            "tests/test_app.py": '''from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)

def test_health():
    """Saglik endpoint testi."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
''',
        }
    },
    "flet_app": {
        "description": "Flet mobil/masaustu sablonu",
        "files": {
            "src/main.py": '''import flet as ft

def main(page: ft.Page):
    page.title = "Flet App"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    txt_number = ft.TextField(value="0", text_align=ft.TextAlign.RIGHT, width=100)

    def minus_click(e):
        txt_number.value = str(int(txt_number.value) - 1)
        page.update()

    def plus_click(e):
        txt_number.value = str(int(txt_number.value) + 1)
        page.update()

    page.add(
        ft.Row(
            [
                ft.IconButton(ft.Icons.REMOVE, on_click=minus_click),
                txt_number,
                ft.IconButton(ft.Icons.ADD, on_click=plus_click),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        ft.ElevatedButton("Merhaba", on_click=lambda _: page.add(ft.Text("Flet'ten Merhaba!")))
    )

ft.app(target=main)
''',
            "requirements.txt": "flet\n",
            "tests/test_app.py": '''def test_flet_import():
    import flet
    assert flet is not None
''',
        }
    },
}


def apply_template(template_name: str, project_path: str) -> dict:
    """Sablonu proje klasorune uygula."""
    if template_name not in TEMPLATES:
        return {"success": False, "error": f"Sablon bulunamadi: {template_name}"}

    template = TEMPLATES[template_name]
    root = Path(project_path)
    created = []

    for rel_path, content in template["files"].items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if not full_path.exists():  # Var olan dosyalari silme
            full_path.write_text(content, encoding="utf-8")
            created.append(rel_path)
            print(f"[Template] + {rel_path}")

    return {
        "success": True,
        "template": template_name,
        "created": created,
        "description": template["description"],
    }


def detect_template(goal: str) -> str:
    """Hedef metnine gore uygun sablonu tahmin et."""
    goal_lower = goal.lower()

    if "fastapi" in goal_lower:
        return "fastapi_api"
    # Flet mobil keywords
    if any(w in goal_lower for w in ["flet", "mobil", "mobile", "android", "apk", "ios", "cross-platform"]):
        return "flet_app"
    # Sadece belirgin ise flask_api seç, 'api' veya 'web' gibi jenerik kelimelerde boş bırak
    if any(w in goal_lower for w in ["flask"]):
        return "flask_api"
    if any(w in goal_lower for w in ["sqlite", "veritabani", "database", " db "]):
        return "sqlite_app"
    # CLI: sadece net CLI anahtar kelimeleri
    if any(w in goal_lower for w in ["cli arac", "cli tool", "komut satiri", "command line", "argparse", "click"]):
        return "cli_tool"
    # Tkinter: sadece gorsel GUI kelimeleri
    if any(w in goal_lower for w in ["tkinter", "gui", "pencere", "window", "masaustu"]):
        return "tkinter_gui"
    # Eger hicbiri spesifik degilse sablon yok (bos basla)
    return None
