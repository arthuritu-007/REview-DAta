# Script de Configuración de Entorno - Review Data
# Este script automatiza la instalación de dependencias para Backend y Frontend.

Write-Host "--- Iniciando configuración de Review Data ---" -ForegroundColor Cyan

# 1. Backend
Write-Host "`n[1/3] Configurando Backend (Python)..." -ForegroundColor Yellow
if (!(Test-Path "venv")) {
    Write-Host "Creando entorno virtual..."
    python -m venv venv
}

Write-Host "Instalando dependencias de Python..."
& ".\venv\Scripts\pip" install -r requirements.txt

# 2. Frontend
Write-Host "`n[2/3] Configurando Frontend (Node.js)..." -ForegroundColor Yellow
Set-Location web/frontend
Write-Host "Instalando dependencias de npm..."
npm install
Set-Location ../..

# 3. Variables de Entorno
Write-Host "`n[3/3] Verificando archivo .env..." -ForegroundColor Yellow
if (!(Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Archivo .env creado desde .env.example. POR FAVOR EDITA TUS CREDENCIALES." -ForegroundColor Magenta
    } else {
        Write-Host "ADVERTENCIA: No se encontró .env.example" -ForegroundColor Red
    }
} else {
    Write-Host "El archivo .env ya existe."
}

Write-Host "`n--- Configuración Finalizada ---" -ForegroundColor Green
Write-Host "Usa 'run_reviewdata.bat' para iniciar la aplicación."
pause
