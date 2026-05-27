@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "APPDATA_DIR=%APPDATA%\ReviewData"
set "ENV_FILE=%APPDATA_DIR%\.env"
set "FALLBACK_ENV_FILE=%SCRIPT_DIR%.env"
set "ENV_EXAMPLE_FILE=%SCRIPT_DIR%.env.example"

if not exist "%APPDATA_DIR%" (
  mkdir "%APPDATA_DIR%" >nul 2>nul
)

if exist "%ENV_EXAMPLE_FILE%" (
  call :load_env "%ENV_EXAMPLE_FILE%"
)
if exist "%FALLBACK_ENV_FILE%" (
  call :load_env "%FALLBACK_ENV_FILE%"
)
if exist "%ENV_FILE%" (
  call :load_env "%ENV_FILE%"
)

if defined REVIEWDATA_DB_HOST (
  if /I "!REVIEWDATA_DB_HOST:~0,8!"=="194.238." set "REVIEWDATA_DB_HOST="
  echo !REVIEWDATA_DB_HOST! | findstr /I ".rds.amazonaws.com" >nul && set "REVIEWDATA_DB_HOST="
)
if not defined REVIEWDATA_DB_HOST set "REVIEWDATA_DB_HOST=31.220.92.226"
if /I "%REVIEWDATA_DB_HOST%"=="localhost" goto :host_ok
echo %REVIEWDATA_DB_HOST% | findstr /R "^[0-9][0-9]*\.[0-9]" >nul && goto :host_ok
echo %REVIEWDATA_DB_HOST% | findstr /I "." >nul && goto :host_ok
set "REVIEWDATA_DB_HOST=31.220.92.226"
:host_ok
if not defined REVIEWDATA_DB_PORT set "REVIEWDATA_DB_PORT=5432"
if not defined REVIEWDATA_DB_USER set "REVIEWDATA_DB_USER=reviewdata_user"
if not defined REVIEWDATA_DB_NAME set "REVIEWDATA_DB_NAME=reviewdata"
if not defined REVIEWDATA_DB_SSLMODE (
  echo %REVIEWDATA_DB_HOST% | findstr /I ".rds.amazonaws.com" >nul && set "REVIEWDATA_DB_SSLMODE=require"
)

if defined REVIEWDATA_DB_PASSWORD (
  if /I "%REVIEWDATA_DB_PASSWORD%"=="CAMBIAR_PASSWORD" set "REVIEWDATA_DB_PASSWORD="
)
if not defined REVIEWDATA_DB_PASSWORD set "REVIEWDATA_DB_PASSWORD=Axelob12"
if not defined REVIEWDATA_JWT_SECRET set "REVIEWDATA_JWT_SECRET=reviewdata-dev-secret"

if exist "%APPDATA_DIR%" (
  > "%ENV_FILE%" (
    echo REVIEWDATA_DB_HOST=%REVIEWDATA_DB_HOST%
    echo REVIEWDATA_DB_PORT=%REVIEWDATA_DB_PORT%
    echo REVIEWDATA_DB_USER=%REVIEWDATA_DB_USER%
    echo REVIEWDATA_DB_PASSWORD=%REVIEWDATA_DB_PASSWORD%
    echo REVIEWDATA_DB_NAME=%REVIEWDATA_DB_NAME%
    echo REVIEWDATA_DB_SSLMODE=%REVIEWDATA_DB_SSLMODE%
    echo REVIEWDATA_JWT_SECRET=%REVIEWDATA_JWT_SECRET%
  )
)

set "APP_EXE=%SCRIPT_DIR%ReviewData.exe"
if not exist "%APP_EXE%" set "APP_EXE=%SCRIPT_DIR%dist\ReviewData\ReviewData.exe"

if exist "%APP_EXE%" (
  pushd "%SCRIPT_DIR%"
  start "" "%APP_EXE%"
  popd
  goto :eof
)

pushd "%SCRIPT_DIR%"
python main.py
popd

endlocal

goto :eof

:load_env
for /f "usebackq tokens=1,* delims==" %%A in ("%~1") do (
  set "K=%%A"
  set "V=%%B"
  if not "!K!"=="" (
    if not "!K:~0,1!"=="#" (
      if not "!V!"=="" (
        set "!K!=!V!"
      )
    )
  )
)
goto :eof
