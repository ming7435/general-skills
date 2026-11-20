param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$sourceFile = (Get-Item -LiteralPath $InputPath).FullName
$pdfPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
if ([IO.Path]::GetExtension($sourceFile) -ne '.docx' -or [IO.Path]::GetExtension($pdfPath) -ne '.pdf') {
    throw 'Expected a .docx input and a .pdf output.'
}
$pdfFolder = [IO.Path]::GetDirectoryName($pdfPath)
[void][IO.Directory]::CreateDirectory($pdfFolder)
$temporaryPdf = Join-Path $pdfFolder ('.manual-' + [guid]::NewGuid().ToString('N') + '.pdf')
$wordInstance = $null
$manualDocument = $null
try {
    $wordInstance = New-Object -ComObject Word.Application
    $wordInstance.Visible = $false
    $wordInstance.DisplayAlerts = 0
    $manualDocument = $wordInstance.Documents.Open($sourceFile, $false, $true, $false)
    $manualDocument.ExportAsFixedFormat($temporaryPdf, 17)
    if ((Get-Item -LiteralPath $temporaryPdf).Length -eq 0) { throw 'Word exported an empty PDF.' }
    if ([IO.File]::Exists($pdfPath)) {
        [IO.File]::Replace($temporaryPdf, $pdfPath, [System.Management.Automation.Language.NullString]::Value)
    } else {
        [IO.File]::Move($temporaryPdf, $pdfPath)
    }
    Write-Output $pdfPath
} finally {
    # Word can release its COM server as soon as it closes the final document.
    # A stale proxy during cleanup must not hide the status of the export.
    if ($manualDocument) {
        try { $manualDocument.Close(0) } catch { Write-Verbose $_ }
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($manualDocument) } catch { Write-Verbose $_ }
    }
    if ($wordInstance) {
        try { $wordInstance.Quit(0) } catch { Write-Verbose $_ }
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wordInstance) } catch { Write-Verbose $_ }
    }
    if ([IO.File]::Exists($temporaryPdf)) { [IO.File]::Delete($temporaryPdf) }
}
