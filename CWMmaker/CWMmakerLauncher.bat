@echo off
chcp 65001 >nul
title CWMmaker - Computer Wav Music Maker
cd /d "%~dp0"

echo ============================================================
echo   CWMmaker - Computer Wav Music Maker
echo ============================================================
echo.
echo   当前目录: %CD%
echo.

REM ---- 1. 自动寻找 Python 解释器 ----
set PY_CMD=

REM 优先用 conda 环境里的 python
if exist "%USERPROFILE%\anaconda3\python.exe" (
    set PY_CMD="%USERPROFILE%\anaconda3\python.exe"
    echo   [信息] 使用 Anaconda Python: %USERPROFILE%\anaconda3\python.exe
    goto :found_python
)
if exist "%USERPROFILE%\miniconda3\python.exe" (
    set PY_CMD="%USERPROFILE%\miniconda3\python.exe"
    echo   [信息] 使用 Miniconda Python: %USERPROFILE%\miniconda3\python.exe
    goto :found_python
)
if exist "C:\ProgramData\anaconda3\python.exe" (
    set PY_CMD="C:\ProgramData\anaconda3\python.exe"
    echo   [信息] 使用 Anaconda Python: C:\ProgramData\anaconda3\python.exe
    goto :found_python
)
if exist "C:\ProgramData\miniconda3\python.exe" (
    set PY_CMD="C:\ProgramData\miniconda3\python.exe"
    echo   [信息] 使用 Miniconda Python: C:\ProgramData\miniconda3\python.exe
    goto :found_python
)

REM 尝试 PATH 里的 python
python --version >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=python
    echo   [信息] 使用 PATH 中的 python
    goto :found_python
)

REM 尝试 py launcher
py --version >nul 2>nul
if %errorlevel%==0 (
    set PY_CMD=py
    echo   [信息] 使用 PATH 中的 py
    goto :found_python
)

echo   [错误] 未检测到 Python。
echo          请安装 Python 3.8+ 或 Anaconda。
echo          下载: https://www.python.org/downloads/
echo          安装时务必勾选 "Add Python to PATH"。
echo.
pause
exit /b 1

:found_python
echo.

REM ---- 2. 检查主脚本是否存在 ----
if not exist "CWMmakerRunner.py" (
    echo   [错误] 当前目录下没有找到 CWMmakerRunner.py
    echo          请确保脚本与 bat 文件在同一文件夹。
    echo.
    pause
    exit /b 1
)

REM ---- 3. 检查乐谱文件是否存在 ----
if not exist "SheetMusic.txt" (
    echo   [警告] 未找到 SheetMusic.txt，脚本将提示缺少乐谱。
    echo.
)

REM ---- 4. 检查 numpy ----
%PY_CMD% -c "import numpy" >nul 2>nul
if errorlevel 1 (
    echo   [提示] 未检测到 numpy，正在尝试自动安装...
    echo.

    REM 先试 conda
    where conda >nul 2>nul
    if %errorlevel%==0 (
        echo   [信息] 使用 conda 安装 numpy...
        call conda install -y numpy
        if errorlevel 1 (
            echo   [信息] conda 安装失败，改用 pip...
            %PY_CMD% -m pip install numpy
        )
    ) else (
        echo   [信息] 使用 pip 安装 numpy...
        %PY_CMD% -m pip install numpy
    )

    %PY_CMD% -c "import numpy" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   [错误] numpy 安装失败。
        echo          请手动运行: %PY_CMD% -m pip install numpy
        echo.
        pause
        exit /b 1
    )
    echo   [完成] numpy 安装成功。
    echo.
)

REM ---- 5. 运行主程序 ----
echo ============================================================
echo   启动 CWMmaker...
echo ============================================================
echo.

%PY_CMD% C:\Users\15752\CWMmaker\CWMmakerRunner.py

echo.
echo ============================================================
echo   程序已退出。
echo ============================================================
pause