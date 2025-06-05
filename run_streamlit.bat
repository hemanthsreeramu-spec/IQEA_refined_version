@echo off
SET VENV_DIR=.venv
SET REQUIREMENTS=requirements.txt
SET PYTHON_FILE=action_new_xpath.py

REM Check if virtual environment exists
IF NOT EXIST %VENV_DIR% (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
)

REM Activate the virtual environment
CALL %VENV_DIR%\Scripts\activate

REM Install dependencies
IF EXIST %REQUIREMENTS% (
    python.exe -m pip install --upgrade pip
    echo Installing all dependencies...
    pip install -r %REQUIREMENTS%
) ELSE (
    echo No requirements.txt found, skipping installation.
)

REM Run the Python script
IF EXIST %PYTHON_FILE% (
    echo Running %PYTHON_FILE%...
    set PYTHONUTF8=1
    streamlit run %PYTHON_FILE%
) ELSE (
    echo %PYTHON_FILE% not found.
)

REM Keep the window open
cmd /k
