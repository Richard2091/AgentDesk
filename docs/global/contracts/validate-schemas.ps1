param([string]$SchemaDirectory = "$PSScriptRoot/schema")
$files = Get-ChildItem -LiteralPath $SchemaDirectory -Filter *.json
if ($files.Count -eq 0) { throw "未找到 Schema 文件" }
foreach ($file in $files) { Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json | Out-Null; Write-Output "通过：$($file.Name)" }
