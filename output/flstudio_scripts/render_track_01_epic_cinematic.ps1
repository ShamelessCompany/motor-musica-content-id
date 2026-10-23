# Script de renderizado headless para FL Studio
# Generado automaticamente por el Motor de Musica Procedural

$ErrorActionPreference = "Stop"
$flExe = "C:\Program Files\Image-Line\FL Studio 21\FL64.exe"
$flpProject = "D:\Programacion\motor-musica-content-id\templates\EpicTemplate.flp"
$outDir = "D:\Programacion\motor-musica-content-id\output\audio"

Write-Host "Iniciando renderizado en FL Studio..." -ForegroundColor Cyan
if (-Not (Test-Path $flExe)) {
    Write-Warning "No se encontro FL Studio en '$flExe'. Usar synth_renderer.py como fallback."
    exit 1
}

& $flExe /R /Fwav /O"$outDir" "$flpProject"
Write-Host "Renderizado completado en $outDir" -ForegroundColor Green
