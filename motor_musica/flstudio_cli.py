"""Integracion con FL Studio Headless CLI para Renderizado en Lote.

Permite ejecutar el renderizado en segundo plano sin abrir la interfaz de usuario,
ruteando los canales MIDI a sintetizadores nativos (Sytrus, FLEX, Harmless).
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import List, Optional


STANDARD_FL_PATHS: List[str] = [
    r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 2024\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe",
    r"C:\Program Files (x86)\Image-Line\FL Studio 21\FL64.exe",
    r"C:\Program Files (x86)\Image-Line\FL Studio 20\FL64.exe",
]


@dataclass
class FLStudioRenderResult:
    success: bool
    command_executed: str
    output_audio_path: Optional[str]
    error_message: Optional[str]


class FLStudioCLI:
    """Administrador de comandos CLI para FL Studio en Windows."""

    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = executable_path or self.detect_executable()

    @staticmethod
    def detect_executable() -> Optional[str]:
        """Detecta si FL Studio 64-bit esta instalado en las rutas estandar del sistema."""
        for candidate in STANDARD_FL_PATHS:
            if os.path.isfile(candidate):
                return candidate
        # Intentar buscar en PATH
        in_path = shutil.which("FL64.exe") or shutil.which("FL.exe")
        return in_path

    def is_available(self) -> bool:
        return self.executable_path is not None and os.path.isfile(self.executable_path)

    def build_render_command(
        self,
        project_flp: str,
        output_dir: str,
        audio_format: str = "wav",
    ) -> List[str]:
        """Construye los argumentos para FL64.exe /R /Fwav /Ooutput_dir project.flp."""
        fl_exe = self.executable_path or r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe"
        fmt_flag = f"/F{audio_format.lower()}"
        out_flag = f"/O{output_dir}"
        return [fl_exe, "/R", fmt_flag, out_flag, project_flp]

    def generate_powershell_script(
        self,
        project_flp: str,
        output_dir: str,
        output_ps1_path: str,
    ) -> str:
        """Genera un script .ps1 reutilizable para renderizado desatendido."""
        fl_exe = self.executable_path or r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe"
        content = f"""# Script de renderizado headless para FL Studio
# Generado automaticamente por el Motor de Musica Procedural

$ErrorActionPreference = "Stop"
$flExe = "{fl_exe}"
$flpProject = "{project_flp}"
$outDir = "{output_dir}"

Write-Host "Iniciando renderizado en FL Studio..." -ForegroundColor Cyan
if (-Not (Test-Path $flExe)) {{
    Write-Warning "No se encontro FL Studio en '$flExe'. Usar synth_renderer.py como fallback."
    exit 1
}}

& $flExe /R /Fwav /O"$outDir" "$flpProject"
Write-Host "Renderizado completado en $outDir" -ForegroundColor Green
"""
        with open(output_ps1_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_ps1_path

    def render(
        self,
        project_flp: str,
        output_dir: str,
        timeout_sec: int = 120,
    ) -> FLStudioRenderResult:
        """Ejecuta el renderizado headless si FL Studio esta instalado en el sistema."""
        if not self.is_available():
            cmd_preview = " ".join(self.build_render_command(project_flp, output_dir))
            return FLStudioRenderResult(
                success=False,
                command_executed=cmd_preview,
                output_audio_path=None,
                error_message=(
                    "FL Studio no detectado en el sistema local. "
                    "El motor ha dejado listo el script CLI y usara el sintetizador procedural nativo."
                ),
            )

        cmd = self.build_render_command(project_flp, output_dir)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            if res.returncode == 0:
                expected_filename = Path(project_flp).stem + ".wav"
                out_path = os.path.join(output_dir, expected_filename)
                return FLStudioRenderResult(
                    success=True,
                    command_executed=" ".join(cmd),
                    output_audio_path=out_path if os.path.exists(out_path) else None,
                    error_message=None,
                )
            else:
                return FLStudioRenderResult(
                    success=False,
                    command_executed=" ".join(cmd),
                    output_audio_path=None,
                    error_message=res.stderr or f"Error code {res.returncode}",
                )
        except Exception as e:
            return FLStudioRenderResult(
                success=False,
                command_executed=" ".join(cmd),
                output_audio_path=None,
                error_message=str(e),
            )
