# Utility functions for PowerShell operations

<#
.SYNOPSIS
    Converts a string to uppercase.
.PARAMETER InputString
    The string to convert.
.OUTPUTS
    System.String - The uppercase string.
#>
function Convert-ToUpperCase {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [string]$InputString
    )

    return $InputString.ToUpper()
}

<#
.SYNOPSIS
    Converts a string to lowercase.
.PARAMETER InputString
    The string to convert.
.OUTPUTS
    System.String - The lowercase string.
#>
function Convert-ToLowerCase {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [string]$InputString
    )

    return $InputString.ToLower()
}

<#
.SYNOPSIS
    Removes leading and trailing whitespace from a string.
.PARAMETER InputString
    The string to trim.
.OUTPUTS
    System.String - The trimmed string.
#>
function Remove-Whitespace {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true, ValueFromPipeline = $true)]
        [string]$InputString
    )

    return $InputString.Trim()
}

<#
.SYNOPSIS
    Creates a backup of a file.
.PARAMETER FilePath
    The path to the file to backup.
.PARAMETER BackupDirectory
    The directory where the backup will be created.
.OUTPUTS
    System.String - The path to the backup file.
#>
function Backup-File {
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $false)]
        [string]$BackupDirectory = "."
    )

    if (-not (Test-Path $FilePath)) {
        throw "File not found: $FilePath"
    }

    $fileName = Split-Path $FilePath -Leaf
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupName = "$fileName.$timestamp.bak"
    $backupPath = Join-Path $BackupDirectory $backupName

    Copy-Item -Path $FilePath -Destination $backupPath
    return $backupPath
}

<#
.SYNOPSIS
    Checks if an array contains a specific element.
.PARAMETER Array
    The array to search.
.PARAMETER Element
    The element to find.
.OUTPUTS
    System.Boolean - True if the element is found, false otherwise.
#>
function Test-ArrayContains {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [array]$Array,

        [Parameter(Mandatory = $true)]
        $Element
    )

    return $Array -contains $Element
}

<#
.SYNOPSIS
    Writes a log message with timestamp.
.PARAMETER Message
    The message to log.
.PARAMETER Level
    The log level (Info, Warning, Error).
#>
function Write-LogMessage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,

        [Parameter(Mandatory = $false)]
        [ValidateSet("Info", "Warning", "Error")]
        [string]$Level = "Info"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"

    switch ($Level) {
        "Info" { Write-Host $logEntry -ForegroundColor White }
        "Warning" { Write-Host $logEntry -ForegroundColor Yellow }
        "Error" { Write-Host $logEntry -ForegroundColor Red }
    }
}

<#
.SYNOPSIS
    Validates if a string is a valid email address.
.PARAMETER Email
    The email address to validate.
.OUTPUTS
    System.Boolean - True if the email is valid, false otherwise.
#>
function Test-ValidEmail {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Email
    )

    $emailRegex = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return $Email -match $emailRegex
}

<#
.SYNOPSIS
    Checks if a string is a valid number.
.PARAMETER Value
    The string to check.
.OUTPUTS
    System.Boolean - True if the string is a valid number, false otherwise.
#>
function Test-IsNumber {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $number = 0
    return [double]::TryParse($Value, [ref]$number)
}
