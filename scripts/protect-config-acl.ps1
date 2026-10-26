param(
    [string]$RuntimeRoot='D:\dsbot',
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [ValidateSet('Plan','Apply','Restore')][string]$Mode='Plan',
    [string[]]$ServiceSids=@()
)
# No content changes, credential rotation or recursive filesystem traversal.
# The exact data directory is necessary: AstrBot saves by replacing the file
# with a new temp file, whose ACL otherwise inherits broad directory access.
$ErrorActionPreference='Stop'
function Write-Dacl($Path,$Acl) {
    # Persist only the DACL, not owner/SACL; no SeSecurityPrivilege required.
    $sections=[Security.AccessControl.AccessControlSections]::Access
    $item=Get-Item -LiteralPath $Path
    $only=if($item.PSIsContainer){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
    $only.SetSecurityDescriptorSddlForm($Acl.GetSecurityDescriptorSddlForm($sections),$sections)
    if ($PSVersionTable.PSVersion.Major -ge 6) { [IO.FileSystemAclExtensions]::SetAccessControl($item,$only) }
    else { $item.SetAccessControl($only) }
}
$root=[IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
$targets=@((Join-Path $root 'data'),(Join-Path $root 'data\cmd_config.json'))
$account=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$backup=[IO.Path]::GetFullPath($BackupDirectory)
if ($backup -eq $root -or $backup.TrimEnd('\') -eq (Join-Path $root 'data') -or
    $backup.StartsWith((Join-Path $root 'data')+'\',[StringComparison]::OrdinalIgnoreCase) -or
    $root.StartsWith($backup.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Backup must be outside data directory and cannot be an instance ancestor' }
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$safe=Get-Acl -LiteralPath $backup
$safe.SetAccessRuleProtection($true,$false)
foreach($rule in @($safe.Access)) { $safe.RemoveAccessRuleSpecific($rule) }
foreach($sid in @($account,'S-1-5-18')) {
    $safe.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
}
Write-Dacl $backup $safe
$record=Join-Path $backup 'acl-rollback.json'
if ($Mode -eq 'Restore') {
    $saved=Get-Content -LiteralPath $record -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($saved.root -ne $root) { throw 'Rollback belongs to another instance' }
    foreach($row in @($saved.targets) | Sort-Object { $_.path.Length } -Descending) {
        if ($targets -notcontains $row.path) { throw 'Unexpected rollback target' }
        $acl=Get-Acl -LiteralPath $row.path
        $acl.SetSecurityDescriptorSddlForm($row.sddl,[Security.AccessControl.AccessControlSections]::Access)
        Write-Dacl $row.path $acl
    }
    Write-Output 'Original DACL/inheritance restored; content untouched';exit 0
}
$rows=@()
foreach($target in $targets) {
    $acl=Get-Acl -LiteralPath $target
    $owner=$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    $principals=@($account,'S-1-5-18',$owner)+$ServiceSids | Select-Object -Unique
    $desired=if(Test-Path -LiteralPath $target -PathType Container){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
    $desired.SetAccessRuleProtection($true,$false)
    foreach($sid in $principals) {
        $identity=New-Object Security.Principal.SecurityIdentifier($sid)
        if (Test-Path -LiteralPath $target -PathType Container) {
            $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        } else { $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','Allow') }
        $desired.AddAccessRule($rule)
    }
    $rows+=@{path=$target;sddl=$acl.Sddl;target_sddl=$desired.Sddl}
}
if ($Mode -eq 'Plan') {
    if (Test-Path -LiteralPath $record) { throw 'Existing rollback record must not be overwritten' }
    @{root=$root;targets=$rows;at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $record -Encoding UTF8
    Write-Output 'Plan saved: exact data directory and cmd_config.json; inherited children may be affected. Review service SIDs and rollback before applying.'
    exit 0
}
if (!(Test-Path -LiteralPath $record)) { throw 'Run Plan and review the rollback record first' }
$saved=Get-Content -LiteralPath $record -Raw -Encoding UTF8|ConvertFrom-Json
if ($saved.root -ne $root) { throw 'Plan instance mismatch' }
foreach($row in $saved.targets) {
    if ($targets -notcontains $row.path) { throw 'Unexpected plan target' }
    if ((Get-Acl -LiteralPath $row.path).Sddl -ne $row.sddl) { throw 'ACL changed since Plan; create a fresh reviewed plan' }
}
foreach($row in $saved.targets) {
    $acl=Get-Acl -LiteralPath $row.path
    $acl.SetSecurityDescriptorSddlForm($row.target_sddl,[Security.AccessControl.AccessControlSections]::Access)
    Write-Dacl $row.path $acl
}
Write-Output 'Reviewed DACL applied; verify service reads and atomic saves; rollback file retained'
