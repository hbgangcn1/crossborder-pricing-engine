# 启动物流定价系统
Write-Host "🚀 启动物流定价系统..." -ForegroundColor Green
Write-Host ""

# 激活虚拟环境
& .\.venv\Scripts\Activate.ps1

# 启动Streamlit应用
streamlit run app.py
