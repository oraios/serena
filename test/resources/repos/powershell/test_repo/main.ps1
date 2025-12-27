# Main script demonstrating various PowerShell features

# Import utility functions
. "$PSScriptRoot\utils.ps1"

# Global variables
$Script:ScriptName = "Main Script"
$Script:Counter = 0

<#
.SYNOPSIS
    Greets a user with various greeting styles.
.PARAMETER Username
    The name of the user to greet.
.PARAMETER GreetingType
    The type of greeting (formal, casual, or default).
#>
function Greet-User {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Username,

        [Parameter(Mandatory = $false)]
        [ValidateSet("formal", "casual", "default")]
        [string]$GreetingType = "default"
    )

    switch ($GreetingType) {
        "formal" {
            Write-Output "Good day, $Username!"
        }
        "casual" {
            Write-Output "Hey $Username!"
        }
        default {
            Write-Output "Hello, $Username!"
        }
    }
}

<#
.SYNOPSIS
    Processes an array of items with the specified operation.
.PARAMETER Items
    The array of items to process.
.PARAMETER Operation
    The operation to perform (count, uppercase).
#>
function Process-Items {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Items,

        [Parameter(Mandatory = $true)]
        [ValidateSet("count", "uppercase")]
        [string]$Operation
    )

    foreach ($item in $Items) {
        switch ($Operation) {
            "count" {
                $Script:Counter++
                Write-Output "Processing item $($Script:Counter): $item"
            }
            "uppercase" {
                Write-Output $item.ToUpper()
            }
        }
    }
}

<#
.SYNOPSIS
    Main entry point for the script.
#>
function Main {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [string]$User = "World",

        [Parameter(Mandatory = $false)]
        [string]$Greeting = "default"
    )

    Write-Output "Starting $Script:ScriptName"

    # Use the Greet-User function
    Greet-User -Username $User -GreetingType $Greeting

    # Process some items
    $items = @("item1", "item2", "item3")
    Write-Output "Processing items..."
    Process-Items -Items $items -Operation "count"

    # Use utility functions from utils.ps1
    $upperName = Convert-ToUpperCase -InputString $User
    Write-Output "Uppercase name: $upperName"

    $trimmed = Remove-Whitespace -InputString "  Hello World  "
    Write-Output "Trimmed: '$trimmed'"

    Write-Output "Script completed successfully"
}

# Run main function
Main @args
