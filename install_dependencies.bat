@echo off
echo 📦 安装物流定价系统依赖...
echo.

REM 检查虚拟环境是否存在
if not exist ".venv" (
    echo 创建虚拟环境...
    python -m venv .venv
)

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 升级pip
python -m pip install --upgrade pip

REM 安装核心依赖
echo 安装核心依赖...
pip install -r requirements.txt

REM 安装测试依赖
echo 安装测试依赖...
pip install -r requirements_test.txt

echo.
echo ✅ 依赖安装完成！
echo.
echo 启动应用请运行: start_app.bat
echo 或使用PowerShell: .\start_app.ps1
echo.

pause
