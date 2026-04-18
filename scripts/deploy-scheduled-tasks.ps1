# deploy-scheduled-tasks.ps1
# Deploys Task Scheduler XML sets from GitHub to \Tech Wranglers\ folder
# Accepts: TaskSet (e.g., "MediaPlayers")

param(
    [Parameter(Mandatory = $true)]
    [string]$TaskSet
)

$repoBase = "https://api.github.com/repos/ZanTechTech/msp-scripts/contents/tasks/$TaskSet"
$rawBase  = "https://raw.githubusercontent.com/ZanTechTech/msp-scripts/main/tasks/$TaskSet"
$tsFolder = "\Tech Wranglers\"
$tempDir  = "$env:TEMP\msp-tasks"

# --- Detect auto-login user ---
$autoUser = $null
try {
    $winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    $domain   = (Get-ItemProperty -Path $winlogon -Name DefaultDomainName -ErrorAction Stop).DefaultDomainName
    $username = (Get-ItemProperty -Path $winlogon -Name DefaultUserName -ErrorAction Stop).DefaultUserName
    if ($username) {
        $autoUser = if ($domain) { "$domain\$username" } else { $username }
        Write-Output "[LOG] Detected auto-login user: $autoUser"
    }
} catch {
    Write-Output "[WARN] Could not detect auto-login user from registry"
}

# --- Get task list from GitHub API ---
Write-Output "[LOG] Fetching task set: $TaskSet"
try {
    $listing = Invoke-RestMethod -Uri $repoBase -UseBasicParsing -ErrorAction Stop
    $xmlFiles = $listing | Where-Object { $_.name -like "*.xml" }
} catch {
    Write-Output "[WARN] Failed to list tasks from GitHub: $_"
    return
}

if (-not $xmlFiles -or $xmlFiles.Count -eq 0) {
    Write-Output "[WARN] No XML files found in tasks/$TaskSet/"
    return
}

Write-Output "[LOG] Found $($xmlFiles.Count) task(s) to deploy"

# --- Prepare temp directory ---
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -Path $tempDir -ItemType Directory -Force | Out-Null

# --- Download all XMLs ---
$downloaded = @()
foreach ($file in $xmlFiles) {
    $dlPath = Join-Path $tempDir $file.name
    try {
        Invoke-WebRequest -Uri "$rawBase/$($file.name)" -OutFile $dlPath -UseBasicParsing -ErrorAction Stop
        $downloaded += $dlPath
        Write-Output "[LOG] Downloaded: $($file.name)"
    } catch {
        Write-Output "[WARN] Failed to download $($file.name): $_"
    }
}

if ($downloaded.Count -eq 0) {
    Write-Output "[WARN] No files downloaded — aborting"
    return
}

# --- Wipe existing tasks in \Tech Wranglers\ ---
Write-Output "[LOG] Clearing existing tasks in $tsFolder"
try {
    $existing = Get-ScheduledTask -TaskPath $tsFolder -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Unregister-ScheduledTask -Confirm:$false -ErrorAction Stop
        Write-Output "[LOG] Removed $($existing.Count) existing task(s)"
    } else {
        Write-Output "[LOG] No existing tasks to remove"
    }
} catch {
    Write-Output "[WARN] Error clearing tasks: $_"
}

# --- Deploy each task ---
$passed = 0
$failed = 0

foreach ($xmlPath in $downloaded) {
    $taskName = [System.IO.Path]::GetFileNameWithoutExtension($xmlPath)
    $xmlContent = Get-Content -Path $xmlPath -Raw
    $fullTaskName = "Tech Wranglers\$taskName"
    $isSystem = $xmlContent -match "S-1-5-18"

    if ($isSystem) {
        # SYSTEM task — use schtasks.exe
        Write-Output "[LOG] Deploying (SYSTEM): $taskName"
        try {
            $result = & schtasks.exe /Create /TN "$fullTaskName" /XML "$xmlPath" /RU "SYSTEM" /F 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Output "[LOG] :white_check_mark: $taskName deployed"
                $passed++
            } else {
                Write-Output "[WARN] schtasks failed for $taskName — $result"
                $failed++
            }
        } catch {
            Write-Output "[WARN] Exception deploying $taskName — $_"
            $failed++
        }
    } else {
        # User task — needs auto-login user
        if (-not $autoUser) {
            Write-Output "[WARN] Skipping user task $taskName — no auto-login user detected"
            $failed++
            continue
        }
        Write-Output "[LOG] Deploying (User: $autoUser): $taskName"
        try {
            Register-ScheduledTask -TaskName $fullTaskName -Xml $xmlContent -User $autoUser -Force -ErrorAction Stop | Out-Null
            Write-Output "[LOG] :white_check_mark: $taskName deployed"
            $passed++
        } catch {
            Write-Output "[WARN] Failed to register $taskName — $_"
            $failed++
        }
    }
}

# --- Cleanup ---
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# --- Summary ---
$total = $passed + $failed
Write-Output "[LOG] --- Deploy complete: $passed/$total succeeded ---"
if ($failed -gt 0) {
    Write-Output "[WARN] $failed task(s) failed"
}
