#!/usr/bin/env python

import subprocess

def test_juego_adivinanza():
    # Enviar entradas simuladas por STDIN al subproceso
    simulated_inputs = "\n".join(["50", "25", "75", "10", "90", "1", "100"]) + "\n"
    result = subprocess.run(
        ['python', 'juego_adivinanza.py'],
        input=simulated_inputs,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0 or "¡Bienvenido al juego de adivinanza!" in result.stdout

