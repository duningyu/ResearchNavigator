Set-StrictMode -Version Latest

function ConvertTo-PublicDemoUtcTimestamp($Value) {
  if ($null -eq $Value) { throw 'Process creation time is required.' }
  if ($Value -is [DateTimeOffset]) {
    return $Value.ToUniversalTime()
  }
  if ($Value -is [DateTime]) {
    return ([DateTimeOffset]$Value).ToUniversalTime()
  }
  return [DateTimeOffset]::Parse(
    [string]$Value,
    [Globalization.CultureInfo]::InvariantCulture,
    [Globalization.DateTimeStyles]::RoundtripKind
  ).ToUniversalTime()
}

function Get-PublicDemoCommandLineHash([string] $CommandLine) {
  if (-not $CommandLine) { return $null }
  $bytes = [Text.Encoding]::UTF8.GetBytes($CommandLine)
  $hash = [Security.Cryptography.SHA256]::HashData($bytes)
  return [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Get-PublicDemoRecordValue($Record, [string] $PrimaryName, [string] $FallbackName) {
  $primary = $Record.PSObject.Properties[$PrimaryName]
  if ($primary) { return $primary.Value }
  $fallback = $Record.PSObject.Properties[$FallbackName]
  if ($fallback) { return $fallback.Value }
  return $null
}

function ConvertTo-PublicDemoProcessIdentity($Record) {
  $pidValue = Get-PublicDemoRecordValue $Record 'process_id' 'ProcessId'
  $parentValue = Get-PublicDemoRecordValue $Record 'parent_process_id' 'ParentProcessId'
  $creationValue = Get-PublicDemoRecordValue $Record 'creation_time_utc' 'CreationDate'
  $nameValue = Get-PublicDemoRecordValue $Record 'name' 'Name'
  $executableValue = Get-PublicDemoRecordValue $Record 'executable_path' 'ExecutablePath'
  $commandValue = Get-PublicDemoRecordValue $Record 'command_line' 'CommandLine'
  $created = ConvertTo-PublicDemoUtcTimestamp $creationValue
  return [pscustomobject][ordered]@{
    pid = [int]$pidValue
    parent_pid = [int]$parentValue
    creation_time_utc = $created.ToString('o')
    process_name = [string]$nameValue
    executable_path = [string]$executableValue
    command_line_hash = Get-PublicDemoCommandLineHash ([string]$commandValue)
    command_line = [string]$commandValue
    killable = -not ([string]$nameValue).Equals('conhost.exe', [StringComparison]::OrdinalIgnoreCase)
  }
}

function Get-PublicDemoLiveProcessSnapshot {
  $capturedAt = [DateTimeOffset]::UtcNow
  $records = @(Get-CimInstance Win32_Process | ForEach-Object {
    [pscustomobject][ordered]@{
      process_id = [int]$_.ProcessId
      parent_process_id = [int]$_.ParentProcessId
      creation_time_utc = if ($_.CreationDate) {
        ([DateTimeOffset]$_.CreationDate).ToUniversalTime().ToString('o')
      } else { $null }
      name = [string]$_.Name
      executable_path = [string]$_.ExecutablePath
      command_line = [string]$_.CommandLine
    }
  })
  return [pscustomobject][ordered]@{
    captured_at_utc = $capturedAt.ToString('o')
    processes = $records
  }
}

function Test-PublicDemoProcessIdentity {
  param(
    [Parameter(Mandatory)] $StoredIdentity,
    [Parameter(Mandatory)] [object[]] $Snapshot
  )
  $storedCreatedValue = Get-PublicDemoRecordValue $StoredIdentity 'creation_time_utc' 'creation_time'
  $current = @($Snapshot | Where-Object {
    [int](Get-PublicDemoRecordValue $_ 'process_id' 'ProcessId') -eq [int]$StoredIdentity.pid
  })
  if ($current.Count -ne 1) {
    return [pscustomobject]@{ matched=$false; classification='PROCESS_NOT_FOUND_OR_AMBIGUOUS'; current=$null }
  }
  $identity = ConvertTo-PublicDemoProcessIdentity $current[0]
  $storedCreated = ConvertTo-PublicDemoUtcTimestamp $storedCreatedValue
  $currentCreated = ConvertTo-PublicDemoUtcTimestamp $identity.creation_time_utc
  if ($storedCreated -ne $currentCreated) {
    return [pscustomobject]@{ matched=$false; classification='PID_REUSED'; current=$identity }
  }
  return [pscustomobject]@{ matched=$true; classification='MATCHED'; current=$identity }
}

function Test-PublicDemoOwnershipDisjoint($ComponentResults) {
  $names = @('api','worker','cloudflared')
  $sets = @{}
  foreach ($name in $names) {
    $sets[$name] = @($ComponentResults[$name].accepted_tree | ForEach-Object { [int]$_.pid })
  }
  $overlaps = @()
  for ($left = 0; $left -lt $names.Count; $left++) {
    for ($right = $left + 1; $right -lt $names.Count; $right++) {
      $shared = @($sets[$names[$left]] | Where-Object { $_ -in $sets[$names[$right]] })
      if ($shared.Count -gt 0) {
        $overlaps += [pscustomobject][ordered]@{
          components = "$($names[$left])_$($names[$right])"
          pids = $shared
        }
      }
    }
  }
  return [pscustomobject][ordered]@{
    disjoint = $overlaps.Count -eq 0
    classification = if ($overlaps.Count -eq 0) { 'DISJOINT' } else { 'COMPONENT_OWNERSHIP_SET_OVERLAP' }
    overlaps = $overlaps
  }
}

function Resolve-PublicDemoOwnedProcessTree {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)] [object[]] $Snapshot,
    [Parameter(Mandatory)] [int] $RootPid,
    [Parameter(Mandatory)] $RootCreationTimeUtc,
    [Parameter(Mandatory)] $SnapshotTimeUtc
  )

  $snapshotTime = ConvertTo-PublicDemoUtcTimestamp $SnapshotTimeUtc
  $records = @($Snapshot | ForEach-Object { ConvertTo-PublicDemoProcessIdentity $_ })
  $rootCandidates = @($records | Where-Object { $_.pid -eq $RootPid })
  if ($rootCandidates.Count -ne 1) {
    return [pscustomobject][ordered]@{
      root_trusted = $false
      classification = if ($rootCandidates.Count -eq 0) { 'ROOT_NOT_FOUND' } else { 'ROOT_AMBIGUOUS' }
      accepted_tree = @()
      rejected_edges = @()
    }
  }
  $root = $rootCandidates[0]
  $storedCreated = ConvertTo-PublicDemoUtcTimestamp $RootCreationTimeUtc
  $currentCreated = ConvertTo-PublicDemoUtcTimestamp $root.creation_time_utc
  if ($storedCreated -ne $currentCreated) {
    return [pscustomobject][ordered]@{
      root_trusted = $false
      classification = 'PID_REUSED'
      accepted_tree = @()
      rejected_edges = @([pscustomobject][ordered]@{
        parent_pid = $null
        child_pid = $RootPid
        reason = 'PID_REUSED'
        stored_creation_time_utc = $storedCreated.ToString('o')
        current_creation_time_utc = $currentCreated.ToString('o')
      })
    }
  }
  if ($currentCreated -gt $snapshotTime) {
    return [pscustomobject][ordered]@{
      root_trusted = $false
      classification = 'ROOT_CREATED_AFTER_SNAPSHOT'
      accepted_tree = @()
      rejected_edges = @()
    }
  }

  $accepted = [Collections.Generic.List[object]]::new()
  $rejected = [Collections.Generic.List[object]]::new()
  $queue = [Collections.Generic.Queue[object]]::new()
  $root | Add-Member -NotePropertyName depth -NotePropertyValue 0 -Force
  $accepted.Add($root)
  $queue.Enqueue($root)
  while ($queue.Count -gt 0) {
    $parent = $queue.Dequeue()
    $parentCreated = ConvertTo-PublicDemoUtcTimestamp $parent.creation_time_utc
    $children = @($records | Where-Object { $_.parent_pid -eq $parent.pid } | Sort-Object pid)
    foreach ($child in $children) {
      $childCreated = ConvertTo-PublicDemoUtcTimestamp $child.creation_time_utc
      if ($childCreated -lt $parentCreated) {
        $rejected.Add([pscustomobject][ordered]@{
          parent_pid = $parent.pid
          child_pid = $child.pid
          parent_creation_time_utc = $parentCreated.ToString('o')
          child_creation_time_utc = $childCreated.ToString('o')
          reason = 'IMPOSSIBLE_CAUSAL_PARENT_EDGE'
        })
        continue
      }
      if ($childCreated -gt $snapshotTime) {
        $rejected.Add([pscustomobject][ordered]@{
          parent_pid = $parent.pid
          child_pid = $child.pid
          parent_creation_time_utc = $parentCreated.ToString('o')
          child_creation_time_utc = $childCreated.ToString('o')
          reason = 'CHILD_CREATED_AFTER_SNAPSHOT'
        })
        continue
      }
      $child | Add-Member -NotePropertyName depth -NotePropertyValue ([int]$parent.depth + 1) -Force
      $accepted.Add($child)
      $queue.Enqueue($child)
    }
  }
  return [pscustomobject][ordered]@{
    root_trusted = $true
    classification = 'TRUSTED'
    accepted_tree = @($accepted)
    rejected_edges = @($rejected)
  }
}

Export-ModuleMember -Function @(
  'ConvertTo-PublicDemoUtcTimestamp',
  'Get-PublicDemoCommandLineHash',
  'ConvertTo-PublicDemoProcessIdentity',
  'Get-PublicDemoLiveProcessSnapshot',
  'Test-PublicDemoProcessIdentity',
  'Test-PublicDemoOwnershipDisjoint',
  'Resolve-PublicDemoOwnedProcessTree'
)
