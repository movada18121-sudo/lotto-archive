<#
สั่งงาน Gemini ผ่าน Antigravity CLI (agy) แบบครั้งเดียว แล้วพิมพ์คำตอบ

  .\tools\agy.ps1 -Prompt "คำถาม"                                  # ให้ agy เลือกโมเดลเอง
  .\tools\agy.ps1 -Prompt "..." -Model gemini-4-argon-high          # ดูชื่อโมเดล: agy models
  .\tools\agy.ps1 -Prompt "..." -Effort high
  .\tools\agy.ps1 -Prompt "สร้างภาพ ... ด้วย image-generator" -OutDir assets\gen   # เก็บภาพที่สร้างได้

เรื่องที่สคริปต์นี้จัดการให้:
- เรียก agy.exe ด้วย path เต็ม (เทอร์มินัลที่เปิดค้างไว้ยังไม่มี agy ใน PATH)
- ลบ GEMINI_API_KEY ออกจาก process (ให้ใช้บัญชีที่ล็อกอินไว้ ไม่ใช่คีย์ free tier)
- รันในโฟลเดอร์งานชั่วคราว agy จะได้ไม่แก้ไฟล์ในโปรเจกต์
- print mode มักจบก่อนที่ image-generator ทำเสร็จ และภาพไปอยู่ที่ ~\.gemini\antigravity-cli\brain\<id>\
  ถ้าใส่ -OutDir สคริปต์จะรอภาพใหม่ในนั้นแล้วคัดลอกมาให้
#>
param(
  [Parameter(Mandatory = $true)][string]$Prompt,
  [string]$Model = "",
  [ValidateSet("", "low", "medium", "high", "xhigh", "max")][string]$Effort = "",
  [string]$OutDir = "",
  [int]$TimeoutMin = 10
)
$ErrorActionPreference = "Continue"
$agy = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
if (-not (Test-Path $agy)) { Write-Error "ไม่พบ agy.exe ที่ $agy"; exit 1 }
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue

$work = Join-Path $env:TEMP "agy-work"
New-Item -ItemType Directory -Force $work | Out-Null
$brain = Join-Path $HOME ".gemini\antigravity-cli\brain"
$start = Get-Date

$cliArgs = @("-p", $Prompt, "--print-timeout", "$($TimeoutMin)m", "--mode", "accept-edits")
if ($Model) { $cliArgs += @("--model", $Model) }
if ($Effort) { $cliArgs += @("--effort", $Effort) }

Push-Location $work
try {
  & $agy @cliArgs 2>&1 | ForEach-Object { "$_" } |
    Where-Object { $_ -notmatch "logging before google\.Init" -and $_ -notmatch "terminal sandbox is not available" }
} finally { Pop-Location }

if ($OutDir) {
  New-Item -ItemType Directory -Force $OutDir | Out-Null
  $deadline = (Get-Date).AddMinutes($TimeoutMin)
  $found = @()
  while ((Get-Date) -lt $deadline) {
    $found = @(Get-ChildItem -Path $brain, $work -Recurse -Include *.png, *.jpg, *.jpeg, *.webp -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -gt $start })
    if ($found.Count -gt 0) { Start-Sleep -Seconds 3; break }
    Start-Sleep -Seconds 5
  }
  if ($found.Count -eq 0) { Write-Output "ไม่พบภาพใหม่ภายใน $TimeoutMin นาที"; exit 2 }
  foreach ($f in $found) {
    $dest = Join-Path $OutDir $f.Name
    Copy-Item $f.FullName $dest -Force
    Write-Output "IMAGE: $dest"
  }
}
