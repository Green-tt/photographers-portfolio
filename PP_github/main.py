from fastapi import FastAPI, Request, Form, File, UploadFile, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
import os
import shutil
import json
from typing import List, Optional
from pathlib import Path
from starlette.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
import secrets
from datetime import datetime
import hashlib

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here-change-in-production")

# Добавляем базовую аутентификацию
security = HTTPBasic()

# Создаем папки для хранения файлов
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Файл для хранения пользователей
USERS_FILE = Path("users.json")
CATEGORIES_FILE = Path("categories.json")

# Инициализация файлов если их нет
if not USERS_FILE.exists():
    with open(USERS_FILE, 'w') as f:
        json.dump({
            "admin": {
                "password": hashlib.sha256("admin123".encode()).hexdigest(),
                "role": "admin",
                "created_at": datetime.now().isoformat()
            }
        }, f)

if not CATEGORIES_FILE.exists():
    with open(CATEGORIES_FILE, 'w') as f:
        json.dump(["Природа", "Города", "Животные", "Портреты"], f)

# Сначала монтируем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Функции для работы с пользователями
def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def load_categories():
    with open(CATEGORIES_FILE, 'r') as f:
        return json.load(f)


def save_categories(categories):
    with open(CATEGORIES_FILE, 'w') as f:
        json.dump(categories, f, indent=2)


# Функции аутентификации и авторизации
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        return None
    return user


def is_admin(request: Request):
    user = get_current_user(request)
    return user and user.get("role") == "admin"


# Главная страница
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("about_me.html", {"request": request, "user": get_current_user(request)})


@app.get("/about_me", response_class=HTMLResponse)
async def about_me(request: Request):
    return templates.TemplateResponse("about_me.html", {"request": request, "user": get_current_user(request)})


# Страница галереи
@app.get("/gallery", response_class=HTMLResponse)
async def gallery(request: Request):
    categories = load_categories()

    # Список статических фото
    static_photos = []
    static_img_dir = Path("static/img")
    if static_img_dir.exists():
        for file in static_img_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                # Получаем категорию из метаданных
                meta_file = static_img_dir / f"{file.name}.meta"
                category = "Без категории"
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                        category = meta.get('category', 'Без категории')

                static_photos.append({
                    "url": f"img/{file.name}",
                    "filename": file.name,
                    "type": "static",
                    "category": category
                })

    # Список загруженных фото
    uploaded_photos = []
    if UPLOAD_DIR.exists():
        for file in UPLOAD_DIR.iterdir():
            if file.is_file() and file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                # Получаем категорию из метаданных
                meta_file = UPLOAD_DIR / f"{file.name}.meta"
                category = "Без категории"
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                        category = meta.get('category', 'Без категории')

                uploaded_photos.append({
                    "url": f"uploads/{file.name}",
                    "filename": file.name,
                    "type": "uploaded",
                    "category": category
                })

    return templates.TemplateResponse("gallery.html", {
        "request": request,
        "static_photos": static_photos,
        "uploaded_photos": uploaded_photos,
        "categories": categories,
        "user": get_current_user(request),
        "is_admin": is_admin(request)
    })


# Страница для загрузки фотографий
@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login?next=/upload", status_code=303)

    categories = load_categories()
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "categories": categories,
        "user": get_current_user(request)
    })


# Обработчик загрузки фотографий
@app.post("/upload")
async def upload_photo(
        request: Request,
        category: str = Form("Без категории"),
        files: List[UploadFile] = File(...)
):
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Только администратор может загружать фото")

    uploaded_files = []
    categories = load_categories()

    # Если категории нет в списке, добавляем её
    if category and category != "Без категории" and category not in categories:
        categories.append(category)
        save_categories(categories)

    for file in files:
        # Проверяем, что файл является изображением
        content_type = file.content_type
        if not content_type or not content_type.startswith('image/'):
            continue

        # Создаем безопасное имя файла
        filename = secure_filename(file.filename)
        file_path = UPLOAD_DIR / filename

        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Сохраняем метаданные с категорией
        meta_data = {
            "category": category,
            "uploaded_at": datetime.now().isoformat(),
            "uploaded_by": get_current_user(request)["username"]
        }

        meta_file = UPLOAD_DIR / f"{filename}.meta"
        with open(meta_file, 'w') as f:
            json.dump(meta_data, f)

        uploaded_files.append(filename)

    return RedirectResponse(url="/gallery", status_code=303)


# Обработчик удаления фото
@app.get("/delete/{photo_type}/{filename}")
async def delete_photo(photo_type: str, filename: str, request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Только администратор может удалять фото")

    try:
        if photo_type == "uploaded":
            file_path = UPLOAD_DIR / filename
            meta_file = UPLOAD_DIR / f"{filename}.meta"
        elif photo_type == "static":
            file_path = Path("static/img") / filename
            meta_file = Path("static/img") / f"{filename}.meta"
        else:
            return RedirectResponse(url="/gallery")

        # Проверяем безопасность имени файла
        if ".." in filename or "/" in filename:
            return RedirectResponse(url="/gallery")

        # Удаляем файл и метаданные
        if file_path.exists():
            file_path.unlink()

        if meta_file.exists():
            meta_file.unlink()

        return RedirectResponse(url="/gallery", status_code=303)

    except Exception as e:
        print(f"Ошибка при удалении файла: {e}")
        return RedirectResponse(url="/gallery")


# API для удаления фото
@app.delete("/api/delete/{photo_type}/{filename}")
async def api_delete_photo(photo_type: str, filename: str, request: Request):
    if not is_admin(request):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Только администратор может удалять фото"}
        )

    try:
        if photo_type == "uploaded":
            file_path = UPLOAD_DIR / filename
            meta_file = UPLOAD_DIR / f"{filename}.meta"
        elif photo_type == "static":
            file_path = Path("static/img") / filename
            meta_file = Path("static/img") / f"{filename}.meta"
        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Неверный тип фото"}
            )

        # Проверяем безопасность имени файла
        if ".." in filename or "/" in filename:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Некорректное имя файла"}
            )

        # Проверяем существование файла
        if not file_path.exists():
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Файл не найден"}
            )

        # Удаляем файл и метаданные
        file_path.unlink()
        if meta_file.exists():
            meta_file.unlink()

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Фото успешно удалено"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Ошибка при удалении: {str(e)}"}
        )


# Удаление всех загруженных фото
@app.post("/delete_all_uploaded")
async def delete_all_uploaded(request: Request):
    if not is_admin(request):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Только администратор может удалять фото"}
        )

    try:
        deleted_count = 0
        if UPLOAD_DIR.exists():
            # Удаляем все файлы в папке uploads
            for file in UPLOAD_DIR.iterdir():
                if file.is_file():
                    try:
                        file.unlink()
                        deleted_count += 1
                    except Exception as e:
                        print(f"Ошибка при удалении файла {file}: {e}")

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Удалено {deleted_count} фото",
                "count": deleted_count
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Ошибка при удалении: {str(e)}"}
        )


# Страница регистрации
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "user": get_current_user(request)
    })


@app.post("/register")
async def register_user(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        confirm_password: str = Form(...)
):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пароли не совпадают",
            "user": get_current_user(request)
        })

    users = load_users()

    if username in users:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пользователь уже существует",
            "user": get_current_user(request)
        })

    # Хешируем пароль
    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    users[username] = {
        "password": hashed_password,
        "role": "user",
        "created_at": datetime.now().isoformat()
    }

    save_users(users)

    return RedirectResponse(url="/login", status_code=303)


# Страница входа
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next_url: str = "/"):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next_url": next_url,
        "user": get_current_user(request)
    })


@app.post("/login")
async def login_user(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next_url: str = Form("/")
):
    users = load_users()

    if username not in users:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверное имя пользователя или пароль",
            "next_url": next_url,
            "user": get_current_user(request)
        })

    user_data = users[username]
    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    if user_data["password"] != hashed_password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверное имя пользователя или пароль",
            "next_url": next_url,
            "user": get_current_user(request)
        })

    # Сохраняем пользователя в сессии
    request.session["user"] = {
        "username": username,
        "role": user_data["role"]
    }

    return RedirectResponse(url=next_url, status_code=303)


# Выход
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# Управление категориями (только для админа)
@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login?next=/categories", status_code=303)

    categories = load_categories()
    return templates.TemplateResponse("categories.html", {
        "request": request,
        "categories": categories,
        "user": get_current_user(request)
    })


@app.post("/categories/add")
async def add_category(request: Request, category: str = Form(...)):
    if not is_admin(request):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Только администратор может добавлять категории"}
        )

    categories = load_categories()
    if category not in categories:
        categories.append(category)
        save_categories(categories)

    return RedirectResponse(url="/categories", status_code=303)


@app.post("/categories/delete/{category}")
async def delete_category(request: Request, category: str):
    if not is_admin(request):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Только администратор может удалять категории"}
        )

    categories = load_categories()
    if category in categories:
        categories.remove(category)
        save_categories(categories)

    return RedirectResponse(url="/categories", status_code=303)


# Утилита для безопасного имени файла
def secure_filename(filename: str) -> str:
    import re
    from unicodedata import normalize

    # Нормализуем Unicode
    filename = normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')

    # Удаляем небезопасные символы
    filename = re.sub(r'[^\w\s.-]', '', filename)

    # Заменяем пробелы на подчеркивания
    filename = re.sub(r'[-\s]+', '_', filename)

    # Добавляем временную метку для уникальности
    import time
    name, ext = os.path.splitext(filename)
    timestamp = int(time.time())
    return f"{name}_{timestamp}{ext}"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


