@echo off
cd /d "%~dp0"

echo Activating venv...
call venv\Scripts\activate

echo Starting Streamlit...
streamlit run app.py

pause
