# Invoke-MSPJob.ps1 - The Orchestrator
# Runs scripts, manages Slack threads, handles errors

$ErrorActionPreference = "Stop"

# Config - where everything lives
$script:GitHubBase = "https://raw.githubusercontent.com/ZanTechTech/msp-scripts/main"
$script:GitHubApiBase = "https://api.github.com/repos/ZanTechTech/msp-scripts/contents"

# --- Load Slack Module ---
try {
    iex(iwr "$script:GitHubBase/SlackLog.ps1" -UseBasicParsing)
} catch {
    Write-Error "Failed to load SlackLog.ps1 - cannot continue: $_"
    return
}

# --- Load Manifest ---
try {
    $script:Manifest = (iwr "$script:GitHubBase/scripts.json" -UseBasicParsing).Content | ConvertFrom-Json
} catch {
    Write-Error "Failed to load scripts.json - cannot continue: $_"
    return
}

function Invoke-MSPJob {
    param(
        [string[]]$Scripts,
        [hashtable]$Params = @{}
    )

    $ComputerName = $env:COMPUTERNAME
    $ScriptCount = $Scripts.Count
    $Passed = 0
    $Warned = 0
    $Failed = 0
    $JobStart = Get-Date

    # --- Create parent message in Slack ---
    $Parent = Send-SlackMessage -Text ":wrench: $ComputerName - $ScriptCount script(s) :hourglass_flowing_sand: Running..."
    $ThreadTs = $null
    $ChannelId = $null

    if ($Parent -and $Parent.ok) {
        $ThreadTs = $Parent.ts
        $ChannelId = $Parent.channel
        Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] :arrow_forward: Job started on $ComputerName`nScripts: $($Scripts -join ', ')" -ThreadTs $ThreadTs
    } else {
        Write-Warning "Slack unavailable. Scripts will still run."
    }

    # --- Loop through each script ---
    foreach ($ScriptName in $Scripts) {
        $ScriptStart = Get-Date

        # Look up config in manifest
        $Config = $script:Manifest.$ScriptName

        if (-not $Config) {
            if ($ThreadTs) {
                Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] :x: $ScriptName - not found in scripts.json" -ThreadTs $ThreadTs
            }
            $Failed++
            continue
        }

        # Post script header to thread
        if ($ThreadTs) {
            Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] --- :clipboard: $ScriptName ---" -ThreadTs $ThreadTs
        }

        try {
            # Fetch the script from GitHub
            $ScriptUrl = "$script:GitHubBase/$($Config.path)"
            $ScriptContent = (iwr $ScriptUrl -UseBasicParsing).Content

            # Save to temp file
            $TempFile = Join-Path $env:TEMP "msp-$ScriptName.ps1"
            $ScriptContent | Out-File -FilePath $TempFile -Encoding UTF8 -Force

            # Run it and capture all output
            $Output = & $TempFile @Params 2>&1

            # Process output into lines
            $OutputLines = $Output | Out-String -Stream | Where-Object { $_ -ne "" }

            # Track status for this script
            $ScriptStatus = "passed"

            # Determine what to send to Slack based on outputMode
            $SlackLines = @()
            $AllLines = @()

            foreach ($Line in $OutputLines) {
                $AllLines += $Line

                # Convention mode: only post [LOG] and [WARN] lines
                if ($Config.outputMode -eq "convention") {
                    $logPattern = '^$$LOG$$'
                    $warnPattern = '^$$WARN$$'

                    if ($Line -match $logPattern) {
                        $CleanLine = $Line -replace '^$$LOG$$\s*', ''
                        $SlackLines += $CleanLine
                    }
                    if ($Line -match $warnPattern) {
                        $CleanLine = $Line -replace '^$$WARN$$\s*', ''
                        $SlackLines += ":warning: $CleanLine"
                        $ScriptStatus = "warned"
                    }
                }
                # All mode: post every line
                elseif ($Config.outputMode -eq "all") {
                    $SlackLines += $Line
                }
            }

            # Post collected lines to thread
            if ($ThreadTs -and $SlackLines.Count -gt 0) {
                # Batch lines into chunks to avoid spamming Slack
                $Chunk = ""
                foreach ($Line in $SlackLines) {
                    if (($Chunk.Length + $Line.Length) -gt 2500) {
                        Send-SlackMessage -Text $Chunk -ThreadTs $ThreadTs
                        $Chunk = ""
                    }
                    if ($Chunk -ne "") { $Chunk += "`n" }
                    $Chunk += "[$(Get-Date -Format 'HH:mm:ss')] $Line"
                }
                if ($Chunk -ne "") {
                    Send-SlackMessage -Text $Chunk -ThreadTs $ThreadTs
                }
            }

            # Handle big output
            if ($ThreadTs -and $Config.bigOutput -eq "snippet" -and $AllLines.Count -gt 0) {
                $FullOutput = $AllLines -join "`n"
                Send-SlackSnippet -Content $FullOutput -Filename "$ScriptName-$ComputerName.txt" -Title "$ScriptName full output" -ThreadTs $ThreadTs
            }

            # Duration and status
            $Duration = [math]::Round(((Get-Date) - $ScriptStart).TotalSeconds)

            if ($ScriptStatus -eq "warned") {
                $Warned++
                $Icon = ":warning:"
            } else {
                $Passed++
                $Icon = ":white_check_mark:"
            }

            if ($ThreadTs) {
                Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] --- $Icon $ScriptName complete (${Duration}s) ---" -ThreadTs $ThreadTs
            }

        } catch {
            $Duration = [math]::Round(((Get-Date) - $ScriptStart).TotalSeconds)
            $Failed++

            if ($ThreadTs) {
                Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] :x: $ScriptName FAILED: $($_.Exception.Message) (${Duration}s)" -ThreadTs $ThreadTs
            }

        } finally {
            # Clean up temp file
            if ($TempFile -and (Test-Path $TempFile)) {
                Remove-Item $TempFile -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # --- Job Summary ---
    $TotalDuration = [math]::Round(((Get-Date) - $JobStart).TotalSeconds)

    $SummaryParts = @()
    if ($Passed -gt 0) { $SummaryParts += ":white_check_mark: $Passed passed" }
    if ($Warned -gt 0) { $SummaryParts += ":warning: $Warned warning" }
    if ($Failed -gt 0) { $SummaryParts += ":x: $Failed failed" }
    $SummaryText = $SummaryParts -join ", "

    if ($ThreadTs) {
        Send-SlackMessage -Text "[$(Get-Date -Format 'HH:mm:ss')] :checkered_flag: Job complete: $SummaryText (${TotalDuration}s total)" -ThreadTs $ThreadTs

        # Update the parent message with final status
        $ParentIcon = if ($Failed -gt 0) { ":x:" } elseif ($Warned -gt 0) { ":warning:" } else { ":white_check_mark:" }
        Update-SlackMessage -Text "$ParentIcon $ComputerName - $($Scripts -join ', ') - $SummaryText (${TotalDuration}s)" -Ts $ThreadTs -ChannelId $ChannelId
    }

    Write-Output "Job complete: $SummaryText"
}
