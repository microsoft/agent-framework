<#
.SYNOPSIS
Professional Script to Reinstall and Repair common Windows virtualization features.
.DESCRIPTION
This script runs with Administrator privileges to safely disable and re-enable common virtualization
optional features (Hyper-V, VirtualMachinePlatform, HypervisorPlatform, Microsoft-Windows-Subsystem-Linux, Containers).
#>

# 1. التحقق من صلاحيات المسؤول
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
 Write-Error "خطأ: يجب تشغيل هذا السكربت كمسؤول (Run as Administrator)! (Arabic)\nError: this script must be run as Administrator." 
 Exit 1
}

# 2. قائمة المحاكيات والميزات الافتراضية المستهدفة
$EmulatorFeatures = @(
 "Microsoft-Hyper-V", # محاكي الأجهزة الافتراضية الأساسي
 "VirtualMachinePlatform", # منصة المحاكي وتشغيل تطبيقات أندرويد
 "HypervisorPlatform", # منصة الـ Hypervisor للبرامج الخارجية
 "Microsoft-Windows-Subsystem-Linux", # نظام لينكس الفرعي لمحاكاة بيئات العمل
 "Containers" # الحاويات والمحاكيات المعزولة
)

Write-Host "`n=== بدء عملية إعادة تثبيت وإصلاح المحاكيات وأنظمة الافتراضية ===`n" -ForegroundColor Cyan

# 3. خطوة الحذف النظيف لإصلاح الملفات المعطوبة
foreach ($Feature in $EmulatorFeatures) {
 Write-Progress -Activity "جاري إلغاء التثبيت القديم" -Status "يفحص الآن: $Feature"
 $check = Get-WindowsOptionalFeature -Online -FeatureName $Feature -ErrorAction SilentlyContinue
 
 if ($check -and $check.State -eq "Enabled") {
 Write-Host "[-] جاري تعطيل وإزالة: $Feature لضمان تثبيت نظيف..." -ForegroundColor Yellow
 Disable-WindowsOptionalFeature -Online -FeatureName $Feature -NoRestart -WarningAction SilentlyContinue | Out-Null
 }
}

Write-Host "`n[+] تم تنظيف الميزات السابقة بنجاح. بدء إعادة التثبيت الآن...`n" -ForegroundColor Green
Start-Sleep -Seconds 2

# 4. خطوة إعادة التثبيت والتفعيل من جديد
$RestartRequired = $false
# Track features that failed to reinstall
$failedFeatures = @()

foreach ($Feature in $EmulatorFeatures) {
 Write-Progress -Activity "جاري إعادة التثبيت والتفعيل" -Status "يتم تثبيت: $Feature"
 Write-Host "[+] جاري تثبيت وتفعيل: $Feature ..." -ForegroundColor Cyan
 
 try {
 $result = Enable-WindowsOptionalFeature -Online -FeatureName $Feature -All -NoRestart -ErrorAction Stop
 if ($result.RestartNeeded) {
 $RestartRequired = $true
 }
 Write-Host "[✓] تم تثبيت $Feature بنجاح." -ForegroundColor Green
 }
 catch {
 Write-Warning "[X] فشل تثبيت $Feature. السبب: $_"  # Arabic
 Write-Warning "[X] Failed to enable $Feature. Reason: $_"      # English
 $failedFeatures += $Feature
 }
}

# 5. Finish and notify about restart / إنهاء العملية وإشعار المستخدم بإعادة التشغيل
if ($failedFeatures.Count -gt 0) {
 Write-Host "`n=== تمت العملية مع أخطاء ===" -ForegroundColor Yellow
 Write-Host "The following features failed to enable: $($failedFeatures -join ', ')" -ForegroundColor Yellow
 Write-Host "يرجى مراجعة رسائل التحذير أعلاه أو تشغيل السكربت كمسؤول مع اتصال إنترنت. (Arabic)" -ForegroundColor Yellow
 Exit 1
}

# All features succeeded; proceed with restart logic
Write-Host "`n=== العملية اكتملت بنجاح / Completed successfully ===`n" -ForegroundColor Green

if ($RestartRequired) {
 Write-Host "`n[تنبيه هام] يتطلب النظام إعادة التشغيل لتطبيق التغييرات وتفعيل المحاكيات بالكامل. (Arabic)\nImportant: a restart is required to apply changes and fully enable emulators." -ForegroundColor Magenta
 $Choose = Read-Host "هل تريد إعادة تشغيل الكمبيوتر الآن؟ (Y / N) - Restart now? (Y/N)"
 if ($Choose -eq "Y" -or $Choose -eq "y") {
 Write-Host "جاري إعادة التشغيل الآن... / Restarting now..." -ForegroundColor Yellow
 Restart-Computer
 } else {
 Write-Host "يرجى تذكر إعادة تشغيل الجهاز يدوياً لاحقاً لتعمل المحاكيات بشكل صحيح. / Please remember to restart later to complete changes." -ForegroundColor Yellow
 }
} else {
 Write-Host "المحاكيات مفعّلة وجاهزة للعمل دون الحاجة لإعادة التشغيل. / Emulators enabled and ready without restart." -ForegroundColor Green
}

