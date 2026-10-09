param([string]$Artifact = "dist")
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Artifact -PathType Container)) {
  throw "发布目录不存在: $Artifact"
}
$files = @(Get-ChildItem -LiteralPath $Artifact -Recurse -File)
if ($files.Count -eq 0) { throw "发布目录为空: $Artifact" }

$onWindows = $env:OS -eq "Windows_NT"
$onMac = $IsMacOS -or $env:OSTYPE -like "darwin*"
if ($onWindows) {
  $executables = @($files | Where-Object { $_.Extension -in @('.exe', '.msi') })
  if ($executables.Count -eq 0) { throw "未找到 Windows 安装包或可执行文件" }
  if (-not (Get-Command Get-AuthenticodeSignature -ErrorAction SilentlyContinue)) {
    throw "当前 PowerShell 不支持 Authenticode 验签；请在 Windows PowerShell 5.1 或安装 Microsoft.PowerShell.Security 后重试"
  }
  foreach ($file in $executables) {
    $sig = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($sig.Status -ne "Valid") { throw "未通过 Authenticode: $($file.FullName) ($($sig.Status))" }
  }
}
if ($onMac) {
  if (-not (Get-Command codesign -ErrorAction SilentlyContinue)) { throw "未找到 codesign" }
  $apps = @(Get-ChildItem -LiteralPath $Artifact -Filter *.app -Recurse -Directory)
  $dmgs = @(Get-ChildItem -LiteralPath $Artifact -Filter *.dmg -Recurse -File)
  if ($apps.Count -eq 0 -and $dmgs.Count -eq 0) { throw "未找到 macOS app 或 dmg" }
  foreach ($app in $apps) {
    & codesign --verify --deep --strict --verbose=2 $app.FullName
    if ($LASTEXITCODE -ne 0) { throw "codesign 验证失败: $($app.FullName)" }
    if (Get-Command spctl -ErrorAction SilentlyContinue) {
      & spctl --assess --type execute --verbose=2 $app.FullName
      if ($LASTEXITCODE -ne 0) { throw "Gatekeeper 验证失败: $($app.FullName)" }
    }
  }
  if (Get-Command stapler -ErrorAction SilentlyContinue) {
    foreach ($dmg in $dmgs) {
      & stapler validate $dmg.FullName
      if ($LASTEXITCODE -ne 0) { throw "公证票据验证失败: $($dmg.FullName)" }
    }
  }
}
Write-Host "发布签名验收通过"
