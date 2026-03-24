# start.ps1
# Multi-Agent AI — Otomatik Başlatma Scripti
# Kullanım: powershell -ExecutionPolicy Bypass -File start.ps1

$HOST_DIR   = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT    = $HOST_DIR  # updated: removed AWS refs
$PORT       = 8000

# ── Renkli Banner ──────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Multi-Agent AI — Otomatik Başlatma ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── .env kontrolü ─────────────────────────────────────────────────────────
$envFile = Join-Path $PROJECT ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  ⚠️  .env bulunamadı! Kopyalanıyor..." -ForegroundColor Yellow
    Copy-Item (Join-Path $PROJECT ".env.example") $envFile
    Write-Host "  ✅ .env oluşturuldu — API anahtarlarını ekle." -ForegroundColor Green
}

# ── API Key kontrolü ──────────────────────────────────────────────────────
$envContent = Get-Content $envFile -Raw
if ($envContent -match 'OPENROUTER_API_KEY=your_openrouter') {
    Write-Host "  ⚠️  UYARI: OpenRouter API anahtarı henüz ayarlanmamış!" -ForegroundColor Red
} else {
    Write-Host "  ✅ API anahtarı bulundu." -ForegroundColor Green
}

# ── Yerel IP bul ──────────────────────────────────────────────────────────
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notmatch '^(127|169)' } |
       Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  🌐 Erişim Adresleri:" -ForegroundColor White
Write-Host "     PC         → http://localhost:$PORT" -ForegroundColor Green
Write-Host "     Android    → http://$ip:$PORT" -ForegroundColor Green
Write-Host "     Şifre      → (check .env file)" -ForegroundColor DarkGray
Write-Host ""

# ── Port çakışma kontrolü ─────────────────────────────────────────────────
$portInUse = Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "  ⚠️  Port $PORT zaten kullanımda! Kapatılıyor..." -ForegroundColor Yellow
    $pid8000 = ($portInUse | Select-Object -First 1).OwningProcess
    Stop-Process -Id $pid8000 -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "  ✅ Port temizlendi." -ForegroundColor Green
}

# ── Bağımlılık kontrolü ───────────────────────────────────────────────────
Write-Host "  📦 Bağımlılıklar kontrol ediliyor..." -ForegroundColor White
Set-Location $PROJECT
$uvicornCheck = python -c "import uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  📥 uvicorn yükleniyor..." -ForegroundColor Yellow
    pip install uvicorn fastapi --quiet
}

# ── Sunucuyu başlat ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  🚀 Sunucu başlatılıyor..." -ForegroundColor Cyan
Write-Host "  ▶  Durdurmak için Ctrl+C" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  ════════════════════════════════════════" -ForegroundColor DarkGray
Write-Host ""

Set-Location $PROJECT
python -m uvicorn api.main_api:app --host 0.0.0.0 --port $PORT --reload
