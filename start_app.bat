@echo off
echo 🚀 启动物流定价系统...
echo.

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 启动Streamlit应用
streamlit run app.py

pause
