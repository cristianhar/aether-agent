"""
Monitor de Hardware y VRAM para Ollama en NVIDIA RTX 4060 (6 GB VRAM).
Supervisa la carga de modelos, uso de memoria GPU vs CPU offload y contexto activo.
"""

import os
import subprocess
from typing import Any, Dict, List


def get_hardware_vram_status() -> str:
    """
    Superpoder: Consulta en tiempo real los modelos cargados en Ollama, su tamaño en memoria,
    procesador asignado (100% GPU vs CPU Offload) y ventana de contexto.
    Diseñado específicamente para optimizar la GPU NVIDIA GeForce RTX 4060 de 6 GB VRAM.
    """
    try:
        proc = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        output = proc.stdout.strip()
    except FileNotFoundError:
        return "ℹ️ Ollama no está instalado o no se encuentra en el PATH (Hardware GPU en reposo)."
    except Exception as e:
        return f"❌ Error consultando Ollama ps: {str(e)}"

    if not output:
        return "ℹ️ Ollama está activo pero no hay ningún modelo cargado en memoria VRAM en este momento."

    lines = output.splitlines()
    if len(lines) <= 1:
        return "ℹ️ Ningún modelo ocupando memoria VRAM actualmente (GPU en reposo, 6 GB disponibles)."

    report = [
        "🖥️ **Estado de VRAM / Hardware (NVIDIA GeForce RTX 4060 - 6 GB VRAM):**",
        "```",
        output,
        "```",
    ]

    # Detección de CPU Offloading
    if "CPU" in output and "GPU" not in output:
        report.append("⚠️ **ADVERTENCIA CRÍTICA:** El modelo está ejecutándose 100% en CPU. La inferencia será significativamente más lenta.")
        report.append("👉 Recomendación: Cambia a un modelo más ligero como `qwen2.5-coder:3b` o reduce la ventana de contexto a 4096.")
    elif "CPU" in output and "GPU" in output:
        report.append("⚠️ **AVISO DE DESCARGA PARCIAL:** El modelo excede la VRAM de 6 GB y ha descargado capas a la RAM del sistema.")
        report.append("👉 Recomendación: Cierra aplicaciones que consuman GPU o reduce `num_ctx` a 8192 o 4096.")
    else:
        report.append("✅ **RENDIMIENTO ÓPTIMO:** El modelo está cargado completamente en VRAM CUDA sin offloading a RAM.")

    return "\n".join(report)
