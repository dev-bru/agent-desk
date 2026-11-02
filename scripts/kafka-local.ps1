<#
.SYNOPSIS
  Run a local Kafka broker (KRaft, no Docker) on this Windows PC. Development only.
.DESCRIPTION
  Usage: powershell -File scripts/kafka-local.ps1 <init|start|stop|status|topics>
  init    Prepare the data folder once (.kafka/data). Start does this by itself when needed.
  start   Start the broker in the background. Waits until port 9092 answers.
  stop    Kill the broker process tree that start recorded in .kafka/broker.pid.
  status  Say if the broker runs and if port 9092 answers.
  topics  Create the desk topics. Safe to run again (--if-not-exists).
  Needs Java 21: uses $env:JAVA_HOME, else the newest C:\Program Files\Eclipse Adoptium\jdk-21* folder.
  Uses ports 9092 (clients) and 9093 (controller) on 127.0.0.1 only.
#>
param([Parameter(Mandatory = $true)][ValidateSet('init', 'start', 'stop', 'status', 'topics')][string]$Action)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$KafkaHome = Join-Path $Root '.kafka\kafka_2.13-4.3.2'
$Work = Join-Path $Root '.kafka'
$Data = Join-Path $Work 'data'
$Config = Join-Path $Work 'server.properties'
$PidFile = Join-Path $Work 'broker.pid'
$Log = Join-Path $Work 'broker.out.log'
$Topics = 'desk.tickets', 'desk.work', 'desk.approvals.requests', 'desk.approvals.decisions', 'desk.results', 'desk.dead-letter'

function Find-Java {
    # Already-open shells may not have JAVA_HOME, so look in the usual install folder too.
    if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { return $env:JAVA_HOME }
    $found = Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory -Filter 'jdk-21*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $found) { throw 'Java 21 not found. Install Temurin 21 or set JAVA_HOME.' }
    return $found.FullName
}

# Why not the .bat files in bin\windows? kafka-run-class.bat puts all 109 jars on ONE cmd line. With this
# project path the line is longer than the 8191 character cmd limit ("The input line is too long", MEASURED
# 2026-11-02). So this script starts java itself. The JVM accepts the wildcard libs\* as a class path.
function Get-JavaArgs([string]$Log4jFile, [string]$Class, [string[]]$KafkaArgs) {
    $log4j = "-Dlog4j2.configurationFile=file:" + $KafkaHome.Replace('\', '/') + "/config/$Log4jFile"
    $logs = "-Dkafka.logs.dir=" + (Join-Path $Work 'logs')
    return @($env:KAFKA_HEAP_OPTS -split ' ') + $log4j, $logs, '-cp', (Join-Path $KafkaHome 'libs\*'), $Class + $KafkaArgs
}

function Invoke-Tool([string]$Class, [string[]]$KafkaArgs) {
    $javaArgs = Get-JavaArgs 'tools-log4j2.yaml' $Class $KafkaArgs
    & (Join-Path $env:JAVA_HOME 'bin\java.exe') $javaArgs
}

function Test-Port {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', 9092); return $true } catch { return $false } finally { $client.Close() }
}

function Get-BrokerPid {
    if (-not (Test-Path $PidFile)) { return $null }
    $recorded = [int](Get-Content $PidFile -TotalCount 1)
    # Windows reuses process IDs. Only trust the PID if it is still a java process, so stop never kills another program.
    $process = Get-Process -Id $recorded -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq 'java') { return $recorded }
    return $null
}

function Write-Config {
    # Fill the template. Kafka reads forward slashes on Windows, and a backslash is an escape in .properties files.
    $template = Get-Content (Join-Path $Root 'config\kafka\server.properties') -Raw
    $text = $template.Replace('@DATA_DIR@', $Data.Replace('\', '/'))
    [System.IO.File]::WriteAllText($Config, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Initialize-Storage {
    if (Test-Path (Join-Path $Data 'meta.properties')) { return }
    New-Item -ItemType Directory -Force $Data | Out-Null
    Write-Config
    $id = (Invoke-Tool 'kafka.tools.StorageTool' @('random-uuid') | Select-Object -Last 1).Trim()
    # --standalone makes a one-node controller quorum, so no voter list is needed.
    Invoke-Tool 'kafka.tools.StorageTool' @('format', '--standalone', '-t', $id, '-c', $Config)
    if ($LASTEXITCODE -ne 0) { throw 'kafka-storage setup failed' }
}

if (-not (Test-Path $KafkaHome)) { throw "Kafka binaries not found at $KafkaHome (see README)." }
New-Item -ItemType Directory -Force $Work | Out-Null
$env:JAVA_HOME = Find-Java
if (-not $env:KAFKA_HEAP_OPTS) { $env:KAFKA_HEAP_OPTS = '-Xmx512M -Xms512M' }

switch ($Action) {
    'init' { Initialize-Storage; 'Storage ready.' }
    'start' {
        if (Get-BrokerPid) { 'Broker already running.'; break }
        if (Test-Port) { throw 'Port 9092 is already in use by another process.' }
        Initialize-Storage
        Write-Config
        # The recorded PID is java.exe. stop kills its whole tree anyway.
        $javaArgs = Get-JavaArgs 'log4j2.yaml' 'kafka.Kafka' @($Config)
        $quoted = ($javaArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
        $process = Start-Process -FilePath (Join-Path $env:JAVA_HOME 'bin\java.exe') -ArgumentList $quoted `
            -WindowStyle Hidden -PassThru -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
        Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
        for ($i = 0; $i -lt 60; $i++) {
            if ($process.HasExited) { throw "Broker exited. See $Log and $Log.err" }
            if (Test-Port) { "Broker up (pid $($process.Id))."; return }
            Start-Sleep -Seconds 1
        }
        throw "Broker did not answer on 127.0.0.1:9092 within 60 s. See $Log"
    }
    'stop' {
        $recorded = Get-BrokerPid
        if ($recorded) { taskkill /T /F /PID $recorded | Out-Null; 'Broker stopped.' } else { 'Broker not running.' }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
    'status' {
        $recorded = Get-BrokerPid
        "process: $(if ($recorded) { "running (pid $recorded)" } else { 'not running' })"
        "port 9092: $(if (Test-Port) { 'answers' } else { 'no answer' })"
    }
    'topics' {
        foreach ($topic in $Topics) {
            Invoke-Tool 'org.apache.kafka.tools.TopicCommand' @('--bootstrap-server', '127.0.0.1:9092', '--create', '--if-not-exists',
                '--topic', $topic, '--partitions', '1', '--replication-factor', '1')
            if ($LASTEXITCODE -ne 0) { throw "Could not create $topic" }
        }
    }
}
