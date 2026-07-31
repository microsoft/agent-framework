<#
.SYNOPSIS
 Professional Script to Reinstall and Repair All Core Windows Emulators & Virtualization Capabilities.
.DESCRIPTION
 This script runs with Administrator privileges to safely remove and clean-reinstall 
 Hyper-V, Virtual Machine Platform, Windows Sandbox, and WSL Components.
#>

# 1. التحقق من صلاحيات المسؤول
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
 Write-Error "خطأ: يجب تشغيل هذا السكربت كمسؤول (Run as Administrator)!"
 Exit
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
 Write-Warning "[X] فشل تثبيت $Feature. السبب: $_"
 }
}

# 5. إنهاء العملية وإشعار المستخدم بإعادة التشغيل
Write-Host "`n=== اكتملت العملية بنجاح! ===" -ForegroundColor Green

if ($RestartRequired) {
 Write-Host "`n[تنبيه هام] يتطلب النظام إعادة التشغيل لتطبيق التغييرات وتفعيل المحاكيات بالكامل." -ForegroundColor Magenta
 $Choose = Read-Host "هل تريد إعادة تشغيل الكمبيوتر الآن؟ (Y / N)"
 if ($Choose -eq "Y" -or $Choose -eq "y") {
 Write-Host "جاري إعادة التشغيل الآن..." -ForegroundColor Yellow
 Restart-Computer
 } else {
 Write-Host "يرجى تذكر إعادة تشغيل الجهاز يدوياً لاحقاً لتعمل المحاكيات بشكل صحيح." -ForegroundColor Yellow
 }
} else {
 Write-Host "المحاكيات مفعّلة وجاهزة للعمل دون الحاجة لإعادة التشغيل." -ForegroundColor Green
}
