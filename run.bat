@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"

if not exist "%VENV_DIR%" (
    echo Создаю виртуальное окружение в %VENV_DIR%...
    python -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

if not exist "%VENV_DIR%\.deps_installed" (
    echo Устанавливаю зависимости...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e "%SCRIPT_DIR%."
    type nul > "%VENV_DIR%\.deps_installed"
)

comfygen %*
