"""python312._pth 写入模板四处副本一致性测试。

模板硬编码于 4 处（任一处漂移都会导致 CI 打包产物与本地修复行为不一致）：
  1. .github/workflows/windows-portable.yml（CI 构建时写入）
  2. asr-service/setup.ps1 Repair-EmbeddedPth
  3. manage.ps1 Portable-UpdateDeps
  4. asr-service/setup.bat（cmd echo 块，路径分隔符为反斜杠，语义等价）

纯文本解析，不依赖 PyYAML / Windows 环境。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

GOLDEN = [
    "python312.zip",
    ".",
    "../..",
    "../../lib/site-packages",
    "Lib/site-packages",
    "import site",
]


def _norm(lines: list[str]) -> list[str]:
    """反斜杠归一为正斜杠后比较（bat 与 ps1/yml 分隔符差异属预期）。"""
    return [line.replace("\\", "/").strip() for line in lines]


def _read(rel: str) -> str:
    # utf-8-sig 兼容 ps1 的 BOM；bat 为无 BOM UTF-8
    return (REPO_ROOT / rel).read_text(encoding="utf-8-sig")


def _extract_ps_array(text: str, source: str) -> list[str]:
    m = re.search(r"-Value @\(\s*(.*?)\)\s*-Encoding ASCII", text, re.S)
    assert m, f"{source}: 未找到 Set-Content -Value @(...) -Encoding ASCII 块"
    return re.findall(r"'([^']*)'", m.group(1))


def from_workflow() -> list[str]:
    return _extract_ps_array(
        _read(".github/workflows/windows-portable.yml"), "windows-portable.yml"
    )


def from_setup_ps1() -> list[str]:
    return _extract_ps_array(_read("asr-service/setup.ps1"), "setup.ps1")


def from_manage_ps1() -> list[str]:
    return _extract_ps_array(_read("manage.ps1"), "manage.ps1")


def from_setup_bat() -> list[str]:
    text = _read("asr-service/setup.bat")
    m = re.search(r'> "bin\\python\\%%F" \(\s*(.*?)\n\s*\)', text, re.S)
    assert m, "setup.bat: 未找到 > \"bin\\python\\%%F\" (...) 写入块"
    return [
        line.strip()[len("echo "):].strip()
        for line in m.group(1).splitlines()
        if line.strip().startswith("echo ")
    ]


def test_pth_template_consistent_across_four_copies():
    templates = {
        "windows-portable.yml": from_workflow(),
        "asr-service/setup.ps1": from_setup_ps1(),
        "manage.ps1": from_manage_ps1(),
        "asr-service/setup.bat": from_setup_bat(),
    }
    for name, tpl in templates.items():
        assert len(tpl) == len(GOLDEN), f"{name}: 行数 {len(tpl)} != {len(GOLDEN)}: {tpl}"
        assert _norm(tpl) == GOLDEN, f"{name}: 模板与金标准不一致: {tpl}"


def test_golden_covers_app_import_and_pip_visibility():
    """金标准自身约束：../.. 保证 app 可导入；../../lib/site-packages 保证 pip 可见。"""
    assert "../.." in GOLDEN
    assert "../../lib/site-packages" in GOLDEN
    assert GOLDEN[-1] == "import site"
