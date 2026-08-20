@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: Mirror indexes (China defaults; override with PIP_INDEX_URL / TORCH_INDEX_URL env)
set PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
if not "%PIP_INDEX_URL%"=="" set PIP_INDEX=%PIP_INDEX_URL%

echo ==========================================
echo   Qwen3-ASR Service Windows Setup
echo ==========================================
echo.

:: 1. Detect Python environment
set PYTHON_MODE=
set PYTHON_BIN=

:: Check portable Python (bin\python + lib)
if exist "bin\python\python.exe" (
    if exist "lib\site-packages" (
        bin\python\python.exe -V >nul 2>&1
        if errorlevel 1 (
            echo [WARN] bin\python\python.exe exists but is not executable; falling back
        ) else (
            echo [INFO] Portable Python environment detected, using portable mode
            set PYTHON_MODE=portable
            set PYTHON_BIN=bin\python\python.exe
            set "PIP_TARGET=--target=lib\site-packages"
            goto :python_ready
        )
    )
)

:: No portable environment, ask user
echo.
echo [INFO] Portable Python environment not detected (bin + lib directories missing)
echo.
echo Select Python environment setup method:
echo   1) Download portable package (recommended, ready to use)
echo   2) Use system Python + venv
echo.
set /p ENV_CHOICE="Enter choice [1/2] (default 1): "
if "%ENV_CHOICE%"=="" set ENV_CHOICE=1

if "%ENV_CHOICE%"=="2" goto :setup_venv

:: --- Option 1: Portable package ---
echo.
echo [INFO] Please download the portable package from:
echo.
echo   Baidu Pan: https://pan.baidu.com/s/1ahqW1mxIoNJTG2k6b4PkkA?pwd=6cth
echo   Access code: 6cth
echo.
echo   Download file: qwen3-asr-service-python3.12-pytorch2.6-cu124-bin.7z
echo.
echo [INFO] After extracting, place the bin and lib directories into the asr-service directory:
echo.
echo   asr-service\
echo   +-- bin\
echo   ^|   +-- python\
echo   ^|   ^|   +-- python.exe
echo   ^|   +-- ...
echo   +-- lib\
echo   ^|   +-- site-packages\
echo   ^|       +-- ...
echo   +-- setup.bat
echo   +-- start.bat
echo   +-- ...
echo.
echo [INFO] Once done, run start.bat to launch the service
echo.
pause
exit /b 0

:: --- Option 2: venv ---
:setup_venv
echo.
:: Check system python3/python version
set SYS_PYTHON=
where python >nul 2>&1
if %errorlevel%==0 (
    set SYS_PYTHON=python
) else (
    where python3 >nul 2>&1
    if %errorlevel%==0 (
        set SYS_PYTHON=python3
    )
)

if "%SYS_PYTHON%"=="" (
    echo [ERROR] System Python not found. Please install Python 3.12 first
    echo [ERROR] Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check version is 3.12
for /f "tokens=*" %%v in ('%SYS_PYTHON% -c "import sys;print(chr(46).join(map(str,sys.version_info[:2])))"') do set PY_VER=%%v
echo [INFO] Detected system Python version: %PY_VER%

if not "%PY_VER%"=="3.12" (
    echo.
    echo [ERROR] Current Python version is %PY_VER%, but 3.12 is required
    echo [ERROR] Please download Python 3.12: https://www.python.org/downloads/release/python-31213/
    echo [ERROR] Or use the portable package method - re-run setup.bat and select option 1
    pause
    exit /b 1
)

:: Check existing venv
if exist "venv" (
    echo [INFO] Existing venv virtual environment detected
    set /p REINSTALL_VENV="Delete and reinstall? [y/N]: "
    if /i "!REINSTALL_VENV!"=="y" (
        echo [INFO] Removing old virtual environment...
        rmdir /s /q venv
    ) else if /i "!REINSTALL_VENV!"=="yes" (
        echo [INFO] Removing old virtual environment...
        rmdir /s /q venv
    ) else (
        echo [INFO] Keeping existing virtual environment, skipping creation
        goto :venv_activate
    )
)

echo [INFO] Creating virtual environment...
%SYS_PYTHON% -m venv venv

:venv_activate
call venv\Scripts\activate.bat
set PYTHON_MODE=venv
set PYTHON_BIN=venv\Scripts\python.exe
set "PIP_TARGET="
echo [INFO] venv virtual environment activated

:: Upgrade pip in venv
echo [INFO] Upgrading pip...
%PYTHON_BIN% -m pip install --upgrade pip --index-url %PIP_INDEX%
goto :python_ready

:python_ready
:: Create necessary directories
if not exist "lib\site-packages" (
    if "%PYTHON_MODE%"=="portable" (
        mkdir lib\site-packages
        echo [INFO] Created lib\site-packages
    )
)

:: Detect stray --target=* directories (from previous buggy runs)
if exist "--target=lib" (
    echo [WARN] Found stray directory: --target=lib
    echo [WARN] This was likely created by an earlier buggy version.
    echo [INFO] Run the following command to clean it up:
    echo [INFO]   rd /s /q "--target=lib"
)

:: Fix Embeddable Python ._pth so pip is visible to "python -m pip"
:: (official Embeddable package ships with "#import site" commented out)
if "%PYTHON_MODE%"=="portable" (
    for /f "delims=" %%F in ('dir /b "bin\python\*._pth" 2^>nul') do (
        if not exist "bin\python\%%F.bak" copy /y "bin\python\%%F" "bin\python\%%F.bak" >nul
        echo [INFO] Ensuring import site in %%F ^(Embeddable Python^)...
        > "bin\python\%%F" (
            echo python312.zip
            echo .
            echo ..\..\lib\site-packages
            echo Lib\site-packages
            echo import site
        )
        echo [INFO] %%F fixed
        %PYTHON_BIN% -V >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] _pth rewrite broke Python interpreter; restoring backup
            copy /y "bin\python\%%F.bak" "bin\python\%%F" >nul
            pause
            exit /b 1
        )
    )
)

:: Install pip for portable mode
if "%PYTHON_MODE%"=="portable" (
    %PYTHON_BIN% -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Installing pip...
        if not exist "bin\get-pip.py" (
            echo [INFO] Downloading get-pip.py...
            powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'bin\get-pip.py'"
        )
        if not exist "bin\get-pip.py" (
            echo [ERROR] Failed to download get-pip.py
            echo [ERROR] Please manually download from: https://bootstrap.pypa.io/get-pip.py
            echo [ERROR] Place the file at: %CD%\bin\get-pip.py
            pause
            exit /b 1
        )
        %PYTHON_BIN% bin\get-pip.py --target "lib\site-packages" --index-url %PIP_INDEX%
        if errorlevel 1 (
            echo [ERROR] pip installation failed
            pause
            exit /b 1
        )
        echo [INFO] pip installed
    ) else (
        echo [INFO] pip already installed
    )
)

:: Verify pip is accessible via "python -m pip"
%PYTHON_BIN% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available via "python -m pip"
    echo [INFO] Current sys.path:
    %PYTHON_BIN% -c "import sys; print('\n'.join(sys.path))"
    echo [INFO] Check bin\python\*._pth for correct paths and 'import site'
    pause
    exit /b 1
)
echo [INFO] pip is ready

:: 4. Check CUDA
echo.
echo [INFO] Checking NVIDIA GPU...
nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] NVIDIA GPU detected, will install CUDA PyTorch
    set HAS_GPU=1
    if "!TORCH_INDEX_URL!"=="" (
        set TORCH_INDEX=https://mirrors.aliyun.com/pytorch-wheels/cu124
    ) else (
        set TORCH_INDEX=!TORCH_INDEX_URL!
    )
) else (
    echo [WARN] No GPU detected, will install CPU PyTorch
    set HAS_GPU=0
    if "!TORCH_INDEX_URL!"=="" (
        set TORCH_INDEX=https://mirrors.aliyun.com/pytorch-wheels/cpu
    ) else (
        set TORCH_INDEX=!TORCH_INDEX_URL!
    )
)

:: 5. Model source selection
echo.
echo ==========================================
echo   Model Configuration
echo ==========================================
echo.
echo Select model source:
echo   1) ModelScope (recommended for China)
echo   2) HuggingFace
echo   3) Manual (skip download)
echo.
set /p MODEL_CHOICE="Enter choice [1/2/3] (default 1): "
if "%MODEL_CHOICE%"=="" set MODEL_CHOICE=1

if "%MODEL_CHOICE%"=="1" (
    set MODEL_SOURCE=modelscope
    echo [INFO] Selected ModelScope
) else if "%MODEL_CHOICE%"=="2" (
    set MODEL_SOURCE=huggingface
    echo [INFO] Selected HuggingFace
) else if "%MODEL_CHOICE%"=="3" (
    set MODEL_SOURCE=manual
    echo [INFO] Selected manual mode
    echo.
    echo ==========================================
    echo   Manual Model Placement Guide
    echo ==========================================
    echo.
    echo Place model files in these directories:
    echo.
    echo   ASR 0.6B: %CD%\models\asr\0.6b\
    echo   ASR 1.7B: %CD%\models\asr\1.7b\
    echo   Align:    %CD%\models\align\0.6b\
    echo   VAD:      %CD%\models\vad\fsmn\
    echo   Punc:     %CD%\models\punc\ct-transformer\
    echo.
    echo Download from:
    echo   https://modelscope.cn/models/Qwen/Qwen3-ASR-0.6B
    echo   https://modelscope.cn/models/Qwen/Qwen3-ASR-1.7B
    echo.
    goto :end
) else (
    set MODEL_SOURCE=modelscope
    echo [INFO] Invalid option, using ModelScope
)

:: 6. Install PyTorch
echo.
echo [INFO] Installing PyTorch 2.6.0 (this may take several minutes)...
if "%HAS_GPU%"=="1" (
    %PYTHON_BIN% -m pip install %PIP_TARGET% torch==2.6.0+cu124 torchaudio==2.6.0+cu124 --index-url %PIP_INDEX% --find-links %TORCH_INDEX%
) else (
    %PYTHON_BIN% -m pip install %PIP_TARGET% torch torchaudio --index-url %PIP_INDEX% --find-links %TORCH_INDEX%
)
if errorlevel 1 (
    echo [ERROR] PyTorch installation failed
    echo [INFO] CUDA wheels (torch==2.6.0+cu124) are fetched from:
    echo [INFO]   %TORCH_INDEX%
    echo [INFO] If this mirror is unreachable, set TORCH_INDEX_URL to a custom mirror,
    echo [INFO] or run without GPU (CPU version will be installed automatically).
    pause
    exit /b 1
)
echo [INFO] PyTorch installed

:: 7. Install other dependencies
echo.
echo [INFO] Installing project dependencies...
%PYTHON_BIN% -m pip install %PIP_TARGET% -r requirements.txt --index-url %PIP_INDEX%
if errorlevel 1 (
    echo [ERROR] Dependency installation failed
    pause
    exit /b 1
)
echo [INFO] Dependencies installed

:: 8. Self-check (portable mode only): verify torch and funasr importable
if "%PYTHON_MODE%"=="portable" (
    echo [INFO] Verifying installation...
    %PYTHON_BIN% -c "import torch, funasr; print(torch.__version__)" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Installation verification failed: torch or funasr not importable
        echo [INFO] Run: %PYTHON_BIN% -c "import torch, funasr; print(torch.__version__)"
        echo [INFO] to diagnose missing dependencies
    ) else (
        echo [INFO] Installation verified: torch and funasr are importable
    )
)

:end
echo.
echo ==========================================
echo   Setup Complete
echo ==========================================
echo.
echo To start the service:
echo   start.bat --model-source %MODEL_SOURCE%
echo.
echo Or with custom options:
echo   start.bat --device cuda --model-size 0.6b --model-source %MODEL_SOURCE%
echo.
pause
