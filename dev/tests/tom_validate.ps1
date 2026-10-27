<#
.SYNOPSIS
  Optional check: load a generated semantic model package with Microsoft's Tabular Object Model (TOM).

.DESCRIPTION
  Developer-only, run on your own machine if you choose. It downloads the Microsoft-published NuGet package
  Microsoft.AnalysisServices.NetCore.retail.amd64 into a cache folder, loads the TOM libraries, unzips the
  model package to a temporary folder and calls TmdlSerializer.DeserializeDatabaseFromFolder on the TMDL
  definition folder, the same parser Power BI tools use. TMDL syntax or reference errors are reported with
  their location. Needs PowerShell 7 or later and internet access to nuget.org.

.EXAMPLE
  pwsh dev/tests/tom_validate.ps1 -Package C:\temp\Sales_Analytics_Model_v1_pbip.zip
#>
param(
    [Parameter(Mandatory = $true)] [string]$Package,
    [string]$Version = '19.84.1',
    [string]$CacheDir = (Join-Path ([IO.Path]::GetTempPath()) 'tom-nuget')
)
$ErrorActionPreference = 'Stop'
$lib = Join-Path $CacheDir 'pkg/lib/netcoreapp3.0'
if (-not (Test-Path (Join-Path $lib 'Microsoft.AnalysisServices.Tabular.dll'))) {
    New-Item -ItemType Directory -Force $CacheDir | Out-Null
    $zip = Join-Path $CacheDir "tom.$Version.zip"
    $url = "https://api.nuget.org/v3-flatcontainer/microsoft.analysisservices.netcore.retail.amd64/$Version/microsoft.analysisservices.netcore.retail.amd64.$Version.nupkg"
    Invoke-WebRequest $url -OutFile $zip
    Expand-Archive $zip -DestinationPath (Join-Path $CacheDir 'pkg') -Force
}
foreach ($n in 'Microsoft.AnalysisServices.Runtime.Core', 'Microsoft.AnalysisServices.Runtime.Windows', 'Microsoft.AnalysisServices.Core',
               'Microsoft.AnalysisServices', 'Microsoft.AnalysisServices.Tabular.Json', 'Microsoft.AnalysisServices.Tabular') {
    Add-Type -Path (Join-Path $lib "$n.dll")
}
$work = Join-Path ([IO.Path]::GetTempPath()) ('tomcheck_' + [guid]::NewGuid().ToString('N'))
Expand-Archive $Package -DestinationPath $work
try {
    $def = Get-ChildItem -Recurse -Directory $work | Where-Object { $_.Name -eq 'definition' -and $_.Parent.Name -like '*.SemanticModel' } | Select-Object -First 1
    if (-not $def) { throw "No <name>.SemanticModel/definition folder in $Package" }
    $db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder($def.FullName)
    $m = $db.Model
    'TOM loaded the model: {0} tables, {1} relationships, {2} shared expressions' -f $m.Tables.Count, $m.Relationships.Count, $m.Expressions.Count
    foreach ($t in $m.Tables) {
        '  {0}: {1} columns, {2} measures, {3} partitions' -f $t.Name, $t.Columns.Count, $t.Measures.Count, $t.Partitions.Count
    }
    exit 0
}
catch {
    'TMDL error: ' + $_.Exception.Message
    exit 1
}
finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
