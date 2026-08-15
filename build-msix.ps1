param(
    [string]$Version = "0.2.3.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$sdkBin = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64"
$makeAppx = Join-Path $sdkBin "makeappx.exe"

if (-not (Test-Path $makeAppx)) {
    throw "O Windows SDK com MakeAppx não foi encontrado."
}

$packageRoot = Join-Path $env:TEMP "AizenAutoEditor-msix-package"
$output = Join-Path $root "release\Aizen-Auto-Editor-$Version.msix"
$dist = Join-Path $root "dist\Aizen Auto Editor"


if (-not (Test-Path (Join-Path $dist "Aizen Auto Editor.exe"))) {
    throw "O executável não foi encontrado. Execute build-windows.bat antes."
}

Remove-Item -Recurse -Force $packageRoot -ErrorAction SilentlyContinue
Remove-Item -Force $output -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $packageRoot, (Join-Path $packageRoot "Assets") | Out-Null
Copy-Item (Join-Path $dist "*") $packageRoot -Recurse -Force

# A distribuição pela Store recebe atualizações pelo próprio Windows; o
# atualizador GitHub usado na versão instalável não deve executar aqui.
$updateConfig = Join-Path $packageRoot "_internal\config\update.json"
if (Test-Path $updateConfig) {
    $updateSettings = Get-Content $updateConfig -Raw | ConvertFrom-Json
    $updateSettings.auto_install = $false
    $updateSettings | ConvertTo-Json -Depth 8 | Set-Content $updateConfig -Encoding UTF8
}

$manifest = Get-Content (Join-Path $root "msix\AppxManifest.xml") -Raw
$manifest = $manifest -replace 'Version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"', "Version=`"$Version`""
Set-Content (Join-Path $packageRoot "AppxManifest.xml") $manifest -Encoding UTF8

@'
from pathlib import Path
from io import BytesIO
import base64
from PIL import Image, ImageDraw

root = Path(r"__PACKAGE_ROOT__")
icon = Image.open(BytesIO(base64.b64decode("__ICON_B64__")))
icon.seek(0)
icon = icon.convert("RGBA")

def logo(name, size, padding=0.12):
    canvas = Image.new("RGBA", size, "#08090d")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=max(6, size[0] // 12), fill="#241519")
    usable = min(size) * (1 - padding * 2)
    resized = icon.copy()
    resized.thumbnail((int(usable), int(usable)), Image.Resampling.LANCZOS)
    x, y = (size[0] - resized.width) // 2, (size[1] - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))
    canvas.save(root / "Assets" / name)

logo("Square44x44Logo.png", (44, 44), 0.08)
logo("Square150x150Logo.png", (150, 150))
logo("Square310x310Logo.png", (310, 310))
logo("StoreLogo.png", (50, 50), 0.08)
logo("Wide310x150Logo.png", (310, 150), 0.16)
logo("SplashScreen.png", (620, 300), 0.18)
'@.Replace("__PACKAGE_ROOT__", $packageRoot).Replace("__ICON_B64__", [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $root "assets\aizen-stream-control.ico")))) | python
if ($LASTEXITCODE -ne 0) { throw "A criação dos ícones MSIX falhou." }

& $makeAppx pack /d $packageRoot /p $output /o /nv
if ($LASTEXITCODE -ne 0) { throw "A criação do pacote MSIX falhou." }

Write-Host "Pacote criado em: $output"
