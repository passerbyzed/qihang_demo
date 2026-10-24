@echo off
chcp 65001 >nul
cls
echo ================================================
echo 启航家庭教育 AI 原型 - 一键启动
echo ================================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 检查依赖...
pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 首次运行，正在安装依赖...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)

echo [2/4] 检查 API Key...
if "%DEEPSEEK_API_KEY%"=="" (
    echo [警告] 未配置 DEEPSEEK_API_KEY 环境变量
    echo.
    echo 请选择配置方式:
    echo   1. 临时配置（本次运行有效）
    echo   2. 修改 app.py 永久配置
    echo   3. 跳过（使用 app.py 中的默认值）
    echo.
    choice /c 123 /n /m "请输入选项 (1/2/3): "

    if %errorlevel%==1 (
        set /p DEEPSEEK_API_KEY="请输入您的 DeepSeek API Key: "
        echo [提示] API Key 已临时配置
    )
    if %errorlevel%==2 (
        echo [提示] 请手动编辑 app.py 第 15 行
        notepad app.py
        pause
    )
    if %errorlevel%==3 (
        echo [提示] 将使用 app.py 中的默认值
    )
)

echo [3/4] 启动后端服务...
echo.
echo ================================================
echo 后端服务地址: http://localhost:5000
echo 模拟器地址:   file:///%CD%\simulator.html
echo 原型地址:     file:///%CD%\pm02-prototype-demo.html
echo ================================================
echo.
echo [提示] 按 Ctrl+C 可停止服务
echo.

start "" "simulator.html"
timeout /t 2 /nobreak >nul

python app.py

pause
