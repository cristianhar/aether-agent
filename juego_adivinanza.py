#!/usr/bin/env python

import random


def adivina_el_numero():
    numero_secreto = random.randint(1, 100)
    intentos = 0

    print("¡Bienvenido al juego de adivinanza!"
          "Estoy pensando en un número entre 1 y 100."
          "Tienes 5 intentos para adivinarlo.")

    for i in range(1, 6):
        intento = int(input(f"Intento {i}: Ingresa tu suposición: "))
        intentos += 1

        if intento < numero_secreto:
            print("Muy bajo. Intenta de nuevo.")
        elif intento > numero_secreto:
            print("Muy alto. Intenta de nuevo.")
        else:
            print(f"¡Felicidades! Adivinaste el número en {intentos} intentos")
            return

    print(f"Lo siento, no adivinaste el número. Era {numero_secreto}")

if __name__ == "__main__":
    adivina_el_numero()