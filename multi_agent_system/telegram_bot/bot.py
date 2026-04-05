"""
Telegram Bot: Multi-Agent sistemini Telegram üzerinden yönetir.

Kullanım:
1. @BotFather'dan bot oluştur, token al
2. .env dosyasına TELEGRAM_BOT_TOKEN=... ekle
3. python telegram_bot/bot.py
"""
import asyncio
import io
import logging
import os
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sistemin kök dizini
SYSTEM_ROOT = Path(__file__).parent.parent


def _safe_slug(slug: str) -> str:
    """Sanitize project slug to prevent path traversal."""
    import re
    # Remove path separators and traversal patterns
    cleaned = slug.replace("..", "").replace("/", "").replace("\\", "")
    # Only allow alphanumeric, hyphens, underscores
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", cleaned)
    return cleaned or "invalid-slug"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlatma komutu."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Bilinmiyor"
    first_name = update.effective_user.first_name or "Bilinmiyor"
    
    logger.info(f"🚀 /start komutu | User ID: {user_id} | Username: @{username} | İsim: {first_name}")
    
    await update.message.reply_text(
        f"🤖 Multi-Agent Yazılım Sistemi\n\n"
        f"👤 Senin Telegram ID'n: `{user_id}`\n"
        f"📝 Kullanıcı adın: @{username}\n\n"
        f"Bir hedef yaz, sistem otomatik kod üretsin.\n\n"
        f"Örnek:\n"
        f"  Python ile hesap makinesi yaz\n"
        f"  Flask ile REST API yaz\n"
        f"  SQLite ile görev yöneticisi yaz\n\n"
        f"Komutlar:\n"
        f"  /start - Bu mesajı göster\n"
        f"  /status - Sistem durumu\n"
        f"  /projeler - Son 5 proje\n"
        f"  /build <açıklama> - Flet projesi üret + APK derle",
        parse_mode="Markdown"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sistem durumunu göster."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Bilinmiyor"
    
    logger.info(f"📊 /status komutu | User ID: {user_id} | Username: @{username}")
    
    workspace = SYSTEM_ROOT / "workspace" / "projects"
    project_count = len(list(workspace.iterdir())) if workspace.exists() else 0
    
    await update.message.reply_text(
        f"⚙️ Sistem Durumu\n\n"
        f"✅ Çalışıyor\n"
        f"📁 Toplam proje: {project_count}\n"
        f"🤖 Ajanlar: Planner, Researcher, Coder, Critic, Executor\n"
        f"💰 Maliyet: ~$0.01-0.03/proje"
    )


async def projeler_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Son 5 projeyi listele (Memory Agent kullanarak)."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Bilinmiyor"
    
    logger.info(f"📁 /projeler komutu | User ID: {user_id} | Username: @{username}")
    
    try:
        # V5: Memory Agent kullan
        import sys
        sys.path.insert(0, str(SYSTEM_ROOT))
        from core.memory_agent import get_memory_agent
        
        memory = get_memory_agent()
        projects = memory.list_all()[:5]
        
        if not projects:
            await update.message.reply_text("Henüz proje yok.")
            return
        
        text = "📁 Son Projeler:\n\n"
        for p in projects:
            slug = p.get("slug", "")
            goal = p.get("goal", "")[:50]
            files_count = len(p.get("files", []))
            cost = p.get("cost", 0)
            created = p.get("created_at", "")[:10]
            tags = ", ".join(p.get("tags", [])[:3])
            
            text += f"• {goal}\n"
            text += f"  📅 {created} | 📄 {files_count} dosya | 💰 ${cost:.4f}\n"
            if tags:
                text += f"  🏷️ {tags}\n"
            text += "\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Memory hatası: {e}")
        # Fallback: Eski yöntem
        workspace = SYSTEM_ROOT / "workspace" / "projects"
        if not workspace.exists():
            await update.message.reply_text("Henüz proje yok.")
            return
        
        projects = sorted(
            [p for p in workspace.iterdir() if p.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:5]
        
        if not projects:
            await update.message.reply_text("Henüz proje yok.")
            return
        
        text = "📁 Son Projeler:\n\n"
        for p in projects:
            summary_file = p / "project_summary.txt"
            cost_info = ""
            if summary_file.exists():
                content = summary_file.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    if "Maliyet" in line or "Cost" in line:
                        cost_info = line.strip()
                        break
            text += f"• {p.name[:40]}\n"
            if cost_info:
                text += f"  {cost_info}\n"
        
        await update.message.reply_text(text)


def _is_flet_project(project_path: Path) -> bool:
    """Proje Flet kullanıyor mu kontrol et."""
    src_dir = project_path / "src"
    if not src_dir.exists():
        return False
    for py_file in src_dir.glob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if "import flet" in content or "from flet" in content:
                return True
        except Exception:
            pass
    return False


def _find_apk(project_path: Path) -> Path | None:
    """APK dosyasını bul."""
    for apk in project_path.rglob("*.apk"):
        return apk
    # ASCII build dizininde de ara
    slug = project_path.name
    ascii_dir = Path(r"C:\flet_build") / slug
    for apk in ascii_dir.rglob("*.apk"):
        return apk
    return None


async def build_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flet projeksi üret ve APK derle — /build <açıklama>"""
    ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))  # Set in .env
    user_id = update.effective_user.id
    username = update.effective_user.username or "Bilinmiyor"

    logger.info(f"🔨 /build komutu | User ID: {user_id} | @{username}")

    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Erişim reddedildi.")
        return

    # Açıklamayı al
    goal_parts = context.args
    if not goal_parts:
        await update.message.reply_text(
            "Kullanım: /build <proje açıklaması>\n\n"
            "Örnek: /build Flet ile basit hesap makinesi"
        )
        return

    raw_goal = " ".join(goal_parts).strip()
    # Flet vurgusu ekle — MAOS bunu Flet projesi olarak üretsin
    if "flet" not in raw_goal.lower():
        goal = f"Flet ile {raw_goal} (mobil uygulama, APK derlenecek)"
    else:
        goal = raw_goal

    status_msg = await update.message.reply_text(
        f"⏳ Build devam ediyor...\n\n"
        f"📋 Hedef: {goal[:80]}\n\n"
        f"🧠 MAOS proje kodunu üretiyor..."
    )

    try:
        import sys
        sys.path.insert(0, str(SYSTEM_ROOT))
        from main import run_goal_async

        log_messages: list[str] = []

        async def log_callback(message: str):
            log_messages.append(message)
            if len(log_messages) % 4 == 0:
                preview = "\n".join(log_messages[-4:])
                try:
                    await status_msg.edit_text(
                        f"⏳ Build devam ediyor...\n\n"
                        f"📋 Hedef: {goal[:60]}\n\n"
                        f"```\n{preview[:300]}\n```",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        # Adım 1: MAOS ile proje kodu üret
        result = await run_goal_async(goal, log_callback=log_callback)
        project_slug = _safe_slug(result.get("project_slug", ""))
        cost = result.get("cost_usd", 0)

        if not project_slug or project_slug == "invalid-slug":
            await status_msg.edit_text(
                f"❌ Proje üretilemedi.\n\n{str(result)[:200]}"
            )
            return

        project_path = SYSTEM_ROOT / "workspace" / "projects" / project_slug
        is_flet = _is_flet_project(project_path)

        if not is_flet:
            # Flet değil — sadece ZIP gönder
            await status_msg.edit_text(
                f"✅ Proje üretildi (Flet algılanmadı — ZIP gönderiliyor)\n\n"
                f"📋 Hedef: {goal[:60]}\n"
                f"💰 Maliyet: ${cost:.4f}"
            )
            zip_buffer = _create_zip(project_path)
            await update.message.reply_document(
                document=zip_buffer,
                filename=f"{project_slug[:30]}.zip",
                caption="📦 Proje dosyaları (Flet algılanmadı, APK derlenmedi)"
            )
            return

        # Adım 2: Flet APK build
        await status_msg.edit_text(
            f"⏳ Build devam ediyor...\n\n"
            f"📋 Hedef: {goal[:60]}\n"
            f"🔨 Flet algılandı — APK derleniyor (5-15 dk)..."
        )

        from agents.builder_agent import BuilderAgent
        from core.base_agent import Task as AgentTask
        from core.message_bus import bus

        builder = BuilderAgent(bus=bus)
        build_task = AgentTask(
            task_id="telegram_build",
            description=f"Flet APK derle: {goal}",
            assigned_to="builder",
            context={
                "project_dir": str(project_path),
                "project_slug": project_slug,
            },
        )
        try:
            build_response = await asyncio.wait_for(builder.run(build_task), timeout=300)
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                f"⚠️ Build zaman asimi (5 dk) — ZIP gonderiliyor\n\n"
                f"📋 Hedef: {goal[:60]}\n"
                f"💰 Maliyet: ${cost:.4f}"
            )
            zip_buffer = _create_zip(project_path)
            await update.message.reply_document(
                document=zip_buffer,
                filename=f"{project_slug[:30]}.zip",
                caption="📦 Proje kaynak kodu (build zaman asimina ugradi)"
            )
            return

        # Adım 3: APK'yı bul ve gönder
        apk_path = _find_apk(project_path)
        if apk_path and apk_path.exists():
            await status_msg.edit_text(
                f"✅ APK hazır!\n\n"
                f"📋 Hedef: {goal[:60]}\n"
                f"💰 Toplam maliyet: ${cost:.4f}\n"
                f"📦 APK boyutu: {apk_path.stat().st_size // 1024} KB"
            )
            with open(apk_path, "rb") as apk_file:
                await update.message.reply_document(
                    document=apk_file,
                    filename=f"{project_slug[:25]}.apk",
                    caption=f"🤖 MAOS tarafından derlendi\n💰 ${cost:.4f}"
                )
        else:
            # APK bulunamadı — ZIP gönder
            build_msg = build_response.content.get("result", "Bilinmiyor") if build_response else "Hata"
            await status_msg.edit_text(
                f"⚠️ APK bulunamadı — ZIP gönderiliyor\n\n"
                f"Build sonucu: {str(build_msg)[:200]}\n"
                f"💰 Maliyet: ${cost:.4f}"
            )
            zip_buffer = _create_zip(project_path)
            await update.message.reply_document(
                document=zip_buffer,
                filename=f"{project_slug[:30]}.zip",
                caption="📦 Proje kaynak kodu (APK derlenemedi)"
            )

    except Exception as e:
        logger.error(f"/build hatası: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Build hatası:\n{str(e)[:300]}\n\nTekrar deneyin."
        )


def _create_zip(project_path: Path) -> io.BytesIO:
    """Proje dosyalarını ZIP'e sıkıştır."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ["src", "tests", "docs"]:
            folder_path = project_path / folder
            if folder_path.exists():
                for file in folder_path.rglob("*"):
                    if file.is_file() and file.name != ".gitkeep":
                        arcname = f"{project_path.name}/{file.relative_to(project_path)}"
                        zf.write(file, arcname)
        
        for extra in ["requirements.txt", "project_summary.txt", "plan.json"]:
            extra_path = project_path / extra
            if extra_path.exists():
                zf.write(extra_path, f"{project_path.name}/{extra}")
    
    zip_buffer.seek(0)
    return zip_buffer


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının hedefini al, sistemi çalıştır."""
    # GÜVENLİK: Sadece sen kullanabilirsin
    ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))  # Set in .env
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Bilinmiyor"
    first_name = update.effective_user.first_name or "Bilinmiyor"
    
    # Her erişim denemesini logla
    logger.info(f"📨 Mesaj geldi | User ID: {user_id} | Username: @{username} | İsim: {first_name}")
    
    if user_id != ALLOWED_USER_ID:
        logger.warning(f"⛔ ERİŞİM REDDEDİLDİ | User ID: {user_id} | Username: @{username} | İsim: {first_name}")
        await update.message.reply_text(
            "⛔ Bu bot özel kullanım içindir.\n"
            "Erişim reddedildi.\n\n"
            f"Senin ID'n: {user_id}"
        )
        return
    
    logger.info(f"✅ ERİŞİM ONAYLANDI | User ID: {user_id} (Ahmed)")
    goal = update.message.text.strip()
    
    if not goal or len(goal) < 5:
        await update.message.reply_text("Lütfen daha açıklayıcı bir hedef yaz.")
        return
    
    # Başlangıç mesajı
    status_msg = await update.message.reply_text(
        f"⚡ Çalışıyor...\n\n"
        f"Hedef: {goal[:80]}\n\n"
        f"🧠 Planlıyor..."
    )
    
    try:
        # Orchestrator'ı import et ve çalıştır
        import sys
        sys.path.insert(0, str(SYSTEM_ROOT))
        
        from main import run_goal_async
        
        # Canlı log callback — Telegram'a gönder
        log_messages = []
        
        async def log_callback(message: str):
            log_messages.append(message)
            # Her 3 mesajda bir güncelle (spam olmasın)
            if len(log_messages) % 3 == 0:
                preview = "\n".join(log_messages[-5:])
                try:
                    await status_msg.edit_text(
                        f"⚡ Çalışıyor...\n\n"
                        f"Hedef: {goal[:60]}\n\n"
                        f"```\n{preview[:200]}\n```",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        
        # Sistemi çalıştır
        result = await run_goal_async(goal, log_callback=log_callback)
        
        # Sonuç mesajı
        project_slug = _safe_slug(result.get("project_slug", ""))
        cost = result.get("cost_usd", 0)
        tasks_done = result.get("tasks_completed", 0)
        files_created = len(result.get("task_details", []))
        
        summary = (
            f"✅ Tamamlandı!\n\n"
            f"📋 Görev: {goal[:60]}\n"
            f"✔️ {tasks_done} görev tamamlandı\n"
            f"📄 {files_created} dosya oluşturuldu\n"
            f"💰 Maliyet: ${cost:.4f}\n"
        )
        await status_msg.edit_text(summary)
        
        # ZIP dosyasını gönder
        if project_slug:
            project_path = SYSTEM_ROOT / "workspace" / "projects" / project_slug
            if project_path.exists():
                zip_buffer = _create_zip(project_path)
                await update.message.reply_document(
                    document=zip_buffer,
                    filename=f"{project_slug[:30]}.zip",
                    caption="📦 Proje dosyaları"
                )
    
    except Exception as e:
        logger.error(f"Hata: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Hata oluştu:\n{str(e)[:200]}\n\nTekrar deneyin."
        )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError(".env dosyasında TELEGRAM_BOT_TOKEN bulunamadı!")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("projeler", projeler_command))
    app.add_handler(CommandHandler("build", build_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Telegram Bot başlatıldı. Ctrl+C ile durdur.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
