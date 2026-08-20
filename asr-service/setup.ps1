#Requires -Version 5.1
<#
.SYNOPSIS
    Qwen3-ASR Service Environment Setup (PowerShell)
.DESCRIPTION
    Sets up the Python environment for the ASR service.
    Supports portable Python and system Python + venv modes.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$script:PythonMode = ''
$script:PythonBin = ''
$script:PipTarget = @()
$script:ModelSource = ''

# pip 镜像（可用环境变量覆盖；国内默认走清华 PyPI / 阿里云 pytorch-wheels）
$script:PypiIndex = if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { 'https://pypi.tuna.tsinghua.edu.cn/simple' }
$script:TorchIndex = if ($env:TORCH_INDEX_URL) { $env:TORCH_INDEX_URL } else { 'https://mirrors.aliyun.com/pytorch-wheels/cu124' }

# ============================================================
# Functions (must be defined before use in PowerShell)
# ============================================================

function Show-PortableGuide {
    Write-Host
    Write-Host '[INFO] Please download the portable package from:' -ForegroundColor Cyan
    Write-Host
    Write-Host '  Baidu Pan: https://pan.baidu.com/s/1ahqW1mxIoNJTG2k6b4PkkA?pwd=6cth'
    Write-Host '  Access code: 6cth'
    Write-Host
    Write-Host '  Download file: qwen3-asr-service-python3.12-pytorch2.6-cu124-bin.7z'
    Write-Host
    Write-Host '[INFO] After extracting, place the bin and lib directories into the asr-service directory:' -ForegroundColor Cyan
    Write-Host
    Write-Host '  asr-service\'
    Write-Host '  +-- bin\'
    Write-Host '  ^|   +-- python\'
    Write-Host '  ^|       +-- python.exe'
    Write-Host '  +-- lib\'
    Write-Host '  ^|   +-- site-packages\'
    Write-Host '  +-- setup.ps1'
    Write-Host '  +-- start.ps1'
    Write-Host '  +-- ...'
    Write-Host
    Write-Host '[INFO] Once done, run start.ps1 to launch the service' -ForegroundColor Cyan
    Write-Host
    Read-Host 'Press Enter to exit'
}

function Activate-Venv {
    $script:PythonMode = 'venv'
    $script:PythonBin = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
    $script:PipTarget = @()
    Write-Host '[INFO] venv virtual environment activated' -ForegroundColor Green
}

function Initialize-Venv {
    # Detect system Python
    $sysPython = $null
    $pyCmd = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $sysPython = 'python'
    }
    else {
        $py3Cmd = Get-Command 'python3' -ErrorAction SilentlyContinue
        if ($py3Cmd) { $sysPython = 'python3' }
    }

    if (-not $sysPython) {
        Write-Host '[ERROR] System Python not found. Please install Python 3.12 first' -ForegroundColor Red
        Write-Host '[ERROR] Download: https://www.python.org/downloads/' -ForegroundColor Red
        Read-Host 'Press Enter to exit'
        exit 1
    }

    # Check version
    $pyVer = & $sysPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    Write-Host "[INFO] Detected system Python version: $pyVer" -ForegroundColor Cyan

    if ($pyVer -ne '3.12') {
        Write-Host
        Write-Host "[ERROR] Current Python version is $pyVer, but 3.12 is required" -ForegroundColor Red
        Write-Host '[ERROR] Please download Python 3.12: https://www.python.org/downloads/release/python-31213/' -ForegroundColor Red
        Write-Host '[ERROR] Or use the portable package method - re-run setup.ps1 and select option 1' -ForegroundColor Red
        Read-Host 'Press Enter to exit'
        exit 1
    }

    # Check existing venv
    if (Test-Path 'venv') {
        Write-Host '[INFO] Existing venv virtual environment detected' -ForegroundColor Yellow
        $reinstall = Read-Host 'Delete and reinstall? [y/N]'
        if ($reinstall -in @('y', 'Y', 'yes', 'Yes', 'YES')) {
            Write-Host '[INFO] Removing old virtual environment...' -ForegroundColor Cyan
            Remove-Item -Recurse -Force 'venv'
        }
        else {
            Write-Host '[INFO] Keeping existing virtual environment, skipping creation' -ForegroundColor Cyan
            Activate-Venv
            return
        }
    }

    Write-Host '[INFO] Creating virtual environment...' -ForegroundColor Cyan
    & $sysPython -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERROR] Failed to create virtual environment' -ForegroundColor Red
        Read-Host 'Press Enter to exit'
        exit 1
    }

    Activate-Venv

    # Upgrade pip in venv
    Write-Host '[INFO] Upgrading pip...' -ForegroundColor Cyan
    & $script:PythonBin -m pip install --upgrade pip --index-url $script:PypiIndex 2>$null
}

function Repair-EmbeddedPth {
    if ($script:PythonMode -ne 'portable') { return }

    # 官方 Embeddable Python 默认注释 #import site，导致 pip 对 python -m pip 不可见
    $pth = Get-ChildItem (Join-Path $PSScriptRoot 'bin\python') -Filter 'python3*._pth' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $pth) { return }
    if (Select-String -Path $pth.FullName -Pattern '^import site$' -Quiet) { return }

    Write-Host "[INFO] Enabling import site in $($pth.Name) (Embeddable Python)..." -ForegroundColor Cyan
    if (-not (Test-Path "$($pth.FullName).bak")) {
        Copy-Item $pth.FullName "$($pth.FullName).bak" -Force
    }
    Set-Content -Path $pth.FullName -Value @('python312.zip', '.', '../../lib/site-packages', 'import site') -Encoding ASCII
    Write-Host "[INFO] $($pth.Name) fixed" -ForegroundColor Green
}

function Install-PipIfNeeded {
    if ($script:PythonMode -ne 'portable') { return }

    # Ensure lib\site-packages exists
    $sitePkg = Join-Path $PSScriptRoot 'lib\site-packages'
    if (-not (Test-Path $sitePkg)) {
        New-Item -ItemType Directory -Path $sitePkg -Force | Out-Null
        Write-Host '[INFO] Created lib\site-packages' -ForegroundColor Cyan
    }

    # Check pip in portable
    $pipExe = Join-Path $PSScriptRoot 'bin\python\Scripts\pip.exe'
    if (-not (Test-Path $pipExe)) {
        Write-Host '[INFO] Installing pip...' -ForegroundColor Cyan
        $getPip = Join-Path $PSScriptRoot 'bin\get-pip.py'
        if (-not (Test-Path $getPip)) {
            Write-Host '[INFO] Downloading get-pip.py...' -ForegroundColor Cyan
            Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPip
        }
        & $script:PythonBin $getPip --index-url $script:PypiIndex
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[ERROR] pip installation failed' -ForegroundColor Red
            Read-Host 'Press Enter to exit'
            exit 1
        }
        Write-Host '[INFO] pip installed' -ForegroundColor Green
    }
    else {
        Write-Host '[INFO] pip already installed' -ForegroundColor Green
    }
}

# 提前于 Install-Dependencies 调用：先检测 GPU，有 GPU 时通过 find-links 从 TorchIndex 镜像
# 安装 CUDA 版 torch/torchaudio/torchvision（带依赖），使得后续 Install-Dependencies 中
# requirements.txt 的 torch==2.6.0 约束被 2.6.0+cu124 满足而自动跳过，避免重复下载。
# 无 GPU 或安装失败时返回 $false（Install-Dependencies 装全量 CPU 版兜底），已装 CUDA 版时跳过。
function Install-PyTorch {
    Write-Host
    Write-Host '[INFO] Checking NVIDIA GPU...' -ForegroundColor Cyan

    $hasGpu = $false
    if (Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue) {
        try {
            $null = nvidia-smi 2>&1
            $hasGpu = $LASTEXITCODE -eq 0
        }
        catch { }
    }

    if (-not $hasGpu) {
        Write-Host '[WARN] No GPU detected, using CPU PyTorch from requirements.txt' -ForegroundColor Yellow
        return $false
    }

    # 跳过检查：已装 cu124 版 → 无需重装
    $torchVer = & $script:PythonBin -c "import torch; print(torch.__version__)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $torchVer -like '*+cu124*') {
        Write-Host '[INFO] CUDA PyTorch already installed (' -NoNewline -ForegroundColor Cyan
        Write-Host $torchVer.Trim() -NoNewline -ForegroundColor White
        Write-Host '), skipping' -ForegroundColor Cyan
        return $true
    }

    Write-Host
    Write-Host '[INFO] Installing CUDA PyTorch (this may take several minutes)...' -ForegroundColor Cyan

    $isTarget = $script:PipTarget.Count -gt 0
    if ($isTarget) {
        $sitePkgs = Join-Path $PSScriptRoot 'lib\site-packages'
        foreach ($item in @('torch', 'torchgen', 'torchaudio', 'torchvision')) {
            $dir = Join-Path $sitePkgs $item
            if (Test-Path $dir) { Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue }
        }
        Get-ChildItem $sitePkgs -Directory -Filter 'torch*.dist-info' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^torch[a-z]*-\d' } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }

    # 带依赖安装 CUDA 三件套：torch 的纯 Python 依赖从 PypiIndex 解析，torch wheel
    # 从 TorchIndex 的 find-links 获取（aliyun 平铺页面，非 PEP 503 标准 index）。
    $pipArgs = @('-m', 'pip', 'install') + $script:PipTarget + @(
        'torch==2.6.0+cu124', 'torchaudio==2.6.0+cu124', 'torchvision==0.21.0+cu124',
        '--index-url', $script:PypiIndex, '--find-links', $script:TorchIndex
    )

    & $script:PythonBin @pipArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host
        Write-Host '[WARN] CUDA PyTorch installation failed, falling back to CPU version' -ForegroundColor Yellow
        # 回退清理：确保后续 Install-Dependencies 能装全量 CPU 版
        if ($isTarget) {
            foreach ($item in @('torch', 'torchgen', 'torchaudio', 'torchvision')) {
                $dir = Join-Path $sitePkgs $item
                if (Test-Path $dir) { Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue }
            }
            Get-ChildItem $sitePkgs -Directory -Filter 'torch*.dist-info' -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^torch[a-z]*-\d' } |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
        else {
            & $script:PythonBin -m pip uninstall -y torch torchaudio torchvision 2>$null
        }
        return $false
    }

    Write-Host '[INFO] CUDA PyTorch installed' -ForegroundColor Green

    # 装后自检：CUDA 可用性
    $cudaOk = & $script:PythonBin -c "import torch; print(torch.cuda.is_available())" 2>$null
    if ($cudaOk -notmatch 'True') {
        Write-Host '[WARN] CUDA PyTorch is installed but torch.cuda.is_available() returns False.' -ForegroundColor Yellow
        Write-Host '       This may indicate an outdated NVIDIA driver. Please update your driver.' -ForegroundColor Yellow
    }

    return $true
}

function Install-Dependencies {
    $reqFile = Join-Path $PSScriptRoot 'requirements.txt'
    if (-not (Test-Path $reqFile)) {
        Write-Host '[WARN] requirements.txt not found, skipping dependency installation' -ForegroundColor Yellow
        return
    }

    Write-Host
    Write-Host '[INFO] Installing project dependencies...' -ForegroundColor Cyan
    $pipArgs = @('-m', 'pip', 'install') + $script:PipTarget + @('-r', $reqFile, '--index-url', $script:PypiIndex)
    & $script:PythonBin @pipArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERROR] Dependency installation failed' -ForegroundColor Red
        Read-Host 'Press Enter to exit'
        exit 1
    }
}

function New-Directories {
    $dirs = @(
        'models\asr\0.6b', 'models\asr\1.7b',
        'models\align\0.6b',
        'models\vad\fsmn', 'models\vad\fsmn-onnx',
        'models\punc\ct-transformer', 'models\punc\ct-transformer-onnx',
        'logs', 'data'
    )
    foreach ($dir in $dirs) {
        $path = Join-Path $PSScriptRoot $dir
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
    Write-Host '[INFO] Directories ready' -ForegroundColor Green
}

function Select-ModelSource {
    Write-Host
    Write-Host '==========================================' -ForegroundColor Cyan
    Write-Host '  Model Configuration' -ForegroundColor Cyan
    Write-Host '==========================================' -ForegroundColor Cyan
    Write-Host
    Write-Host 'Select model source:'
    Write-Host '  1) ModelScope (recommended for China, faster download)'
    Write-Host '  2) HuggingFace'
    Write-Host '  3) Manual (skip download, prepare model files yourself)'
    Write-Host

    $choice = Read-Host 'Enter choice [1/2/3] (default 1)'
    if (-not $choice) { $choice = '1' }

    switch ($choice) {
        '1' {
            $script:ModelSource = 'modelscope'
            Write-Host '[INFO] Selected ModelScope' -ForegroundColor Green
        }
        '2' {
            $script:ModelSource = 'huggingface'
            Write-Host '[INFO] Selected HuggingFace' -ForegroundColor Green
        }
        '3' {
            $script:ModelSource = 'manual'
            Write-Host '[INFO] Selected manual mode' -ForegroundColor Cyan
            Write-Host
            Write-Host '==========================================' -ForegroundColor Cyan
            Write-Host '  Manual Model Placement Guide' -ForegroundColor Cyan
            Write-Host '==========================================' -ForegroundColor Cyan
            Write-Host
            Write-Host 'Place model files in these directories:'
            Write-Host
            Write-Host "  ASR 0.6B: $($PSScriptRoot)\models\asr\0.6b\"
            Write-Host "  ASR 1.7B: $($PSScriptRoot)\models\asr\1.7b\"
            Write-Host "  Align:    $($PSScriptRoot)\models\align\0.6b\"
            Write-Host "  VAD:      $($PSScriptRoot)\models\vad\fsmn\"
            Write-Host "  Punc:     $($PSScriptRoot)\models\punc\ct-transformer\"
            Write-Host
            Write-Host 'Download from:'
            Write-Host '  https://modelscope.cn/models/Qwen/Qwen3-ASR-0.6B'
            Write-Host '  https://modelscope.cn/models/Qwen/Qwen3-ASR-1.7B'
            Write-Host '  https://modelscope.cn/models/Qwen/Qwen3-ForcedAligner-0.6B'
            Write-Host '  https://huggingface.co/Qwen/Qwen3-ASR-0.6B'
            Write-Host '  https://huggingface.co/Qwen/Qwen3-ASR-1.7B'
            Write-Host '  https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B'
            Write-Host
        }
        default {
            $script:ModelSource = 'modelscope'
            Write-Host '[INFO] Invalid option, using ModelScope' -ForegroundColor Yellow
        }
    }
}

function Show-SetupComplete {
    $src = if ($script:ModelSource) { $script:ModelSource } else { 'modelscope' }
    Write-Host
    Write-Host '==========================================' -ForegroundColor Green
    Write-Host '  Setup Complete' -ForegroundColor Green
    Write-Host '==========================================' -ForegroundColor Green
    Write-Host
    Write-Host 'To start the service:'
    Write-Host "  .\start.ps1 --model-source $src" -ForegroundColor White
    Write-Host
    Write-Host 'Or with custom options:'
    Write-Host "  .\start.ps1 --device cuda --model-size 0.6b --model-source $src" -ForegroundColor White
    Write-Host
    Read-Host 'Press Enter to exit'
}

# ============================================================
# Main Flow
# ============================================================

Write-Host '==========================================' -ForegroundColor Cyan
Write-Host '  Qwen3-ASR Service Environment Setup' -ForegroundColor Cyan
Write-Host '==========================================' -ForegroundColor Cyan
Write-Host

# --- 1. Detect Python environment ---
$portableDetected = (Test-Path 'bin\python\python.exe') -and (Test-Path 'lib\site-packages')

if ($portableDetected) {
    Write-Host '[INFO] Portable Python environment detected, using portable mode' -ForegroundColor Cyan
    $script:PythonMode = 'portable'
    $script:PythonBin = Join-Path $PSScriptRoot 'bin\python\python.exe'
    $script:PipTarget = @('--target', (Join-Path $PSScriptRoot 'lib\site-packages'))
}
else {
    Write-Host
    Write-Host '[INFO] Portable Python environment not detected (bin + lib directories missing)'
    Write-Host
    Write-Host 'Select Python environment setup method:'
    Write-Host '  1) Download portable package (recommended, ready to use)'
    Write-Host '  2) Use system Python + venv'
    Write-Host

    $envChoice = Read-Host 'Enter choice [1/2] (default 1)'
    if (-not $envChoice) { $envChoice = '1' }

    switch ($envChoice) {
        '1' {
            Show-PortableGuide
            exit 0
        }
        '2' {
            Initialize-Venv
        }
        default {
            Write-Host '[INFO] Invalid option, showing portable guide' -ForegroundColor Yellow
            Show-PortableGuide
            exit 0
        }
    }
}

# --- Common setup (portable or venv) ---
Repair-EmbeddedPth
Install-PipIfNeeded
# 先由 Install-PyTorch 检测 GPU 并预装 CUDA 版 torch（find-links），
# 再装其余依赖（CUDA 版 torch 已满足 requirements.txt 约束，自动跳过，不重复下载）
# 返回值无需处理：失败时 Install-PyTorch 内部已回退清理，Install-Dependencies 装全量 CPU 版兜底
$null = Install-PyTorch
Install-Dependencies
New-Directories
Select-ModelSource
Show-SetupComplete
