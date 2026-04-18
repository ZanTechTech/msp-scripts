# SlackLog.ps1 - Slack communication module
# All Slack interactions go through here. Nothing else touches Slack directly.

$script:SlackToken = "xoxb-10950150851172-10950166386340-2eeSnmpk6OxKTXBLoRQoR9cR
"
$script:SlackChannel = "#msp-logs"
$script:SlackHeaders = @{
    "Authorization" = "Bearer $script:SlackToken"
    "Content-Type"  = "application/json; charset=utf-8"
}

function Send-SlackMessage {
    param(
        [string]$Text,
        [string]$ThreadTs = $null
    )
    
    $Body = @{
        channel = $script:SlackChannel
        text    = $Text
    }
    
    if ($ThreadTs) {
        $Body.thread_ts = $ThreadTs
    }
    
    try {
        $Response = Invoke-RestMethod -Uri "https://slack.com/api/chat.postMessage" `
            -Method POST `
            -Headers $script:SlackHeaders `
            -Body ($Body | ConvertTo-Json -Depth 10)
        
        if ($Response.ok) {
            return $Response
        } else {
            Write-Warning "Slack error: $($Response.error)"
            return $null
        }
    } catch {
        Write-Warning "Slack connection failed: $_"
        return $null
    }
}

function Update-SlackMessage {
    param(
        [string]$Text,
        [string]$Ts,
        [string]$ChannelId
    )
    
    $Body = @{
        channel = $ChannelId
        text    = $Text
        ts      = $Ts
    }
    
    try {
        $Response = Invoke-RestMethod -Uri "https://slack.com/api/chat.update" `
            -Method POST `
            -Headers $script:SlackHeaders `
            -Body ($Body | ConvertTo-Json -Depth 10)
        
        if (-not $Response.ok) {
            Write-Warning "Slack update error: $($Response.error)"
        }
        return $Response
    } catch {
        Write-Warning "Slack update failed: $_"
        return $null
    }
}

function Send-SlackSnippet {
    param(
        [string]$Content,
        [string]$Filename = "output.txt",
        [string]$Title = "Full Output",
        [string]$ThreadTs = $null
    )
    
    $Body = @{
        channels = $script:SlackChannel
        content  = $Content
        filename = $Filename
        title    = $Title
    }
    
    if ($ThreadTs) {
        $Body.thread_ts = $ThreadTs
    }
    
    try {
        Invoke-RestMethod -Uri "https://slack.com/api/files.upload" `
            -Method POST `
            -Headers @{ "Authorization" = "Bearer $script:SlackToken" } `
            -Form $Body
    } catch {
        Write-Warning "Slack snippet upload failed: $_"
    }
}
