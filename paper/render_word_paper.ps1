param(
 [string]$DocumentPath = (Join-Path (Split-Path $PSScriptRoot) 'AR_EAURP_Research_Paper_Revised.docx'),
 [string]$PdfPath = (Join-Path (Split-Path $PSScriptRoot) 'AR_EAURP_Research_Paper_Preview.pdf')
)
$ErrorActionPreference = 'Stop'
$word = $null
$doc = $null
try {
 $word = New-Object -ComObject Word.Application
 $word.Visible = $false
 $word.DisplayAlerts = 0
 $doc = $word.Documents.Open($DocumentPath)
 $doc.Fields.Update() | Out-Null
 foreach ($toc in $doc.TablesOfContents) {
  $toc.Update()
  $toc.Range.Font.Name = 'Times New Roman'
  $toc.Range.Font.Size = 10
  $toc.Range.Font.Bold = 0
  $toc.Range.ParagraphFormat.SpaceAfter = 0
  $toc.Range.ParagraphFormat.SpaceBefore = 0
  $toc.Range.ParagraphFormat.LineSpacingRule = 4
  $toc.Range.ParagraphFormat.LineSpacing = 11.95
  $toc.Range.ParagraphFormat.KeepWithNext = 0
  $toc.Range.ParagraphFormat.RightIndent = 0
 }
 $doc.Repaginate()
 foreach ($toc in $doc.TablesOfContents) { $toc.UpdatePageNumbers() }
 $doc.Save()
 $doc.ExportAsFixedFormat($PdfPath,17)
 Write-Output "Rendered $($doc.ComputeStatistics(2)) pages."
} finally {
 if ($doc) { $doc.Close(0) }
 if ($word) { $word.Quit() }
}
