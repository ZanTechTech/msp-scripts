# kill-windows-nags.ps1
# Silences Windows nags on service machines
# Does NOT uninstall anything — just muzzles the noise
# Re-enable by deleting the registry keys or setting values back

# ── Helper Function ────────────────────────────────────────
function Set-RegistryValue {
    param(
        [string]$Path,
        [string]$Name,
        [object]$Value,
        [string]$Type = "DWord",
        [string]$Label
    )
    try {
        if (-not (Test-Path $Path)) {
            New-Item -Path $Path -Force | Out-Null
        }
        Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type $Type -Force
        Write-Output "[LOG] $Label"
    } catch {
        Write-Output "[WARN] Failed: $Label — $_"
    }
}

# ── HKLM Policy Settings (run directly as SYSTEM) ─────────

Write-Output "[LOG] Applying HKLM policy settings..."

# --- OOBE / Setup ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" `
    -Name "EnableFirstLogonAnimation" -Value 0 `
    -Label "Disabled first logon animation"

# --- Windows Consumer Features / Tips ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent" `
    -Name "DisableWindowsConsumerFeatures" -Value 1 `
    -Label "Disabled Windows consumer features (suggested apps)"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent" `
    -Name "DisableSoftLanding" -Value 1 `
    -Label "Disabled tips and soft landing pages"

# --- Edge ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
    -Name "HideFirstRunExperience" -Value 1 `
    -Label "Edge: disabled first run experience"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
    -Name "DefaultBrowserSettingEnabled" -Value 0 `
    -Label "Edge: disabled default browser nag"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
    -Name "SpotlightExperiencesAndSuggestionsEnabled" -Value 0 `
    -Label "Edge: disabled spotlight and suggestions"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
    -Name "PersonalizationReportingEnabled" -Value 0 `
    -Label "Edge: disabled personalization reporting"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Edge" `
    -Name "ShowRecommendationsEnabled" -Value 0 `
    -Label "Edge: disabled recommendations"

# --- Copilot ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot" `
    -Name "TurnOffWindowsCopilot" -Value 1 `
    -Label "Disabled Windows Copilot"

# --- Cortana ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search" `
    -Name "AllowCortana" -Value 0 `
    -Label "Disabled Cortana"

# --- OneDrive (silence, not kill) ---
Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\OneDrive" `
    -Name "KFMBlockOptIn" -Value 1 `
    -Label "OneDrive: blocked folder backup nag"

Set-RegistryValue -Path "HKLM:\SOFTWARE\Policies\Microsoft\OneDrive" `
    -Name "SilentAccountConfig" -Value 0 `
    -Label "OneDrive: disabled silent account config"

# ── HKCU Settings (via auto-login user's registry hive) ───

Write-Output "[LOG] Detecting auto-login user..."

$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
try {
    $username = (Get-ItemProperty -Path $winlogon -Name DefaultUserName -ErrorAction Stop).DefaultUserName
    $domain = (Get-ItemProperty -Path $winlogon -Name DefaultDomainName -ErrorAction SilentlyContinue).DefaultDomainName
    $autoUser = if ($domain) { "$domain\$username" } else { $username }
    Write-Output "[LOG] Detected auto-login user: $autoUser"
} catch {
    Write-Output "[WARN] No auto-login user detected — skipping HKCU settings"
    Write-Output "[LOG] --- Summary: HKLM policies applied, HKCU skipped ---"
    return
}

# Resolve user SID
try {
    $userAccount = Get-WmiObject Win32_UserAccount | Where-Object { $_.Name -eq $username }
    if (-not $userAccount) { throw "User account not found in WMI" }
    $userSID = $userAccount.SID
    Write-Output "[LOG] User SID: $userSID"
} catch {
    Write-Output "[WARN] Could not resolve SID for $username — $_"
    Write-Output "[LOG] --- Summary: HKLM policies applied, HKCU skipped ---"
    return
}

# Mount HKU if needed
if (-not (Get-PSDrive -Name HKU -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS | Out-Null
}

$hive = "HKU:\$userSID"
if (-not (Test-Path $hive)) {
    Write-Output "[WARN] User hive not loaded at $hive — is user logged in?"
    Write-Output "[LOG] --- Summary: HKLM policies applied, HKCU skipped ---"
    return
}

Write-Output "[LOG] Applying HKCU settings via $hive..."

$cdm = "$hive\SOFTWARE\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"

# --- "You're almost done setting up your PC" ---
Set-RegistryValue -Path "$hive\SOFTWARE\Microsoft\Windows\CurrentVersion\UserProfileEngagement" `
    -Name "ScoobeSystemSettingEnabled" -Value 0 `
    -Label "Disabled 'almost done setting up' nag"

# --- Welcome Experience ---
Set-RegistryValue -Path $cdm -Name "SubscribedContent-310093Enabled" -Value 0 `
    -Label "Disabled Welcome Experience after updates"

# --- Tips about Windows ---
Set-RegistryValue -Path $cdm -Name "SoftLandingEnabled" -Value 0 `
    -Label "Disabled Windows tips"

# --- Suggested content in Settings ---
Set-RegistryValue -Path $cdm -Name "SubscribedContent-338393Enabled" -Value 0 `
    -Label "Disabled suggested content in Settings (338393)"

Set-RegistryValue -Path $cdm -Name "SubscribedContent-353694Enabled" -Value 0 `
    -Label "Disabled suggested content in Settings (353694)"

Set-RegistryValue -Path $cdm -Name "SubscribedContent-353696Enabled" -Value 0 `
    -Label "Disabled suggested content in Settings (353696)"

# --- Start menu suggestions ---
Set-RegistryValue -Path $cdm -Name "SubscribedContent-338388Enabled" -Value 0 `
    -Label "Disabled Start menu suggestions"

Set-RegistryValue -Path $cdm -Name "SystemPaneSuggestionsEnabled" -Value 0 `
    -Label "Disabled system pane suggestions"

# --- Lock screen tips ---
Set-RegistryValue -Path $cdm -Name "RotatingLockScreenEnabled" -Value 0 `
    -Label "Disabled rotating lock screen content"

Set-RegistryValue -Path $cdm -Name "SubscribedContent-338387Enabled" -Value 0 `
    -Label "Disabled lock screen tips"

Write-Output "[LOG] --- Summary: All nag settings applied ---"
