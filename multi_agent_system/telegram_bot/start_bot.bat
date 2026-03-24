@echo off
echo Telegram Bot baslatiliyor...
cd /d "%~dp0.."
python telegram_bot/bot.py
pause
