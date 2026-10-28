param(
    [string]$RuntimeRoot='D:\dsbot',
    [Parameter(Mandatory=$true)][string]$BackupDirectory,
    [ValidateSet('Inspect','Plan','Apply','Restore')][string]$Mode='Inspect',
    [string[]]$ServiceSids=@(),
    [string[]]$RelativeTargets=@('data','data\cmd_config.json')
)
# Inspect is read-only. Plan deliberately writes a private rollback record.
# Directory targets are expanded to an exact reviewed snapshot, including
# original child DACLs: inherited propagation must also be reversible.
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
$targets=New-Object 'Collections.Generic.List[string]'
foreach($relative in $RelativeTargets) {
    if([IO.Path]::IsPathRooted($relative)){throw 'Targets must be instance-relative'}
    $path=[IO.Path]::GetFullPath((Join-Path $root $relative)).TrimEnd('\')
    if($path -ne $root -and !$path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Target escapes instance'}
    $item=Get-Item -LiteralPath $path -Force
    $walk=$item
    while($walk -and $walk.FullName.TrimEnd('\').StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
        if(($walk.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Reparse points are not supported'}
        $walk=$walk.Parent
    }
    $targets.Add($item.FullName)
    if($item.PSIsContainer) {
        foreach($child in Get-ChildItem -LiteralPath $path -Force -Recurse) {
            if(($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'Reparse points are not supported'}
            $targets.Add($child.FullName)
        }
    }
}
$targets=@($targets|Sort-Object -Unique)
$account=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$backup=[IO.Path]::GetFullPath($BackupDirectory)
foreach($target in $targets) {
    if($backup.TrimEnd('\') -eq $target -or $backup.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase) -or
        $target.StartsWith($backup.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Backup must be outside every target subtree and cannot be a target ancestor'}
}
if($Mode -eq 'Inspect') {
    $broad=@($targets|Where-Object {@((Get-Acl -LiteralPath $_).GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {$_.IdentityReference.Value -in @('S-1-1-0','S-1-5-11','S-1-5-32-545') -and $_.AccessControlType -eq 'Allow'}).Count -gt 0})
    @{mode='Inspect';affected_objects=$targets.Count;broad_access_objects=$broad.Count;recursive_directory_snapshot=$true;writes=0;warning='Plan writes backup permissions and rollback JSON; Apply requires separate approval. Review ancestor DeleteSubdirectoriesAndFiles rights.'}|ConvertTo-Json -Compress
    exit 0
}
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
    foreach($row in @($saved.targets) | Sort-Object { $_.path.Length }) {
        if ($targets -notcontains $row.path) { throw 'Unexpected rollback target' }
        $acl=Get-Acl -LiteralPath $row.path
        $acl.SetSecurityDescriptorSddlForm($row.sddl,[Security.AccessControl.AccessControlSections]::Access)
        Write-Dacl $row.path $acl
    }
    Write-Output 'Original DACL/inheritance restored; content untouched';exit 0
}
$rows=New-Object 'Collections.Generic.List[object]'
foreach($target in $targets) {
    $acl=Get-Acl -LiteralPath $target
    $principals=@($account,'S-1-5-18')+$ServiceSids | Select-Object -Unique
    $desired=if(Test-Path -LiteralPath $target -PathType Container){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
    $desired.SetAccessRuleProtection($true,$false)
    foreach($sid in $principals) {
        $identity=New-Object Security.Principal.SecurityIdentifier($sid)
        if (Test-Path -LiteralPath $target -PathType Container) {
            $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        } else { $rule=New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl','Allow') }
        $desired.AddAccessRule($rule)
    }
    $rows.Add(@{path=$target;sddl=$acl.Sddl;target_sddl=$desired.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access)})
}
if ($Mode -eq 'Plan') {
    if (Test-Path -LiteralPath $record) { throw 'Existing rollback record must not be overwritten' }
    @{root=$root;targets=$rows;at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $record -Encoding UTF8
    Write-Output 'Plan saved: exact targets and descendant DACLs. Review service SIDs, ancestor delete rights and rollback before applying.'
    exit 0
}
if (!(Test-Path -LiteralPath $record)) { throw 'Run Plan and review the rollback record first' }
$saved=Get-Content -LiteralPath $record -Raw -Encoding UTF8|ConvertFrom-Json
if ($saved.root -ne $root) { throw 'Plan instance mismatch' }
if((Compare-Object @($saved.targets|ForEach-Object {$_.path}|Sort-Object) @($targets|Sort-Object))){throw 'Target membership changed since Plan; create a fresh reviewed plan'}
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
