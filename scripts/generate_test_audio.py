#!/usr/bin/env python3
"""
Script pour générer un fichier audio WAV de test.
Ce script utilise la bibliothèque scipy pour générer un fichier audio
contenant un signal sinusoïdal simple.
"""
import os
import sys
import numpy as np
from scipy.io import wavfile
from pathlib import Path

def generate_sine_wave(freq, duration, sample_rate):
    """Génère un signal sinusoïdal."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq * t)

def generate_test_audio(output_file, duration=2.0, sample_rate=16000):
    """Génère un fichier audio WAV de test."""
    print(f"Génération d'un fichier audio de test de {duration} secondes...")
    
    # Créer un signal sinusoïdal
    signal = generate_sine_wave(440, duration, sample_rate)  # La 440 Hz
    
    # Normaliser le signal
    signal = signal / np.max(np.abs(signal))
    
    # Convertir en int16
    signal = (signal * 32767).astype(np.int16)
    
    # Créer le répertoire de sortie si nécessaire
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Enregistrer le fichier WAV
    wavfile.write(output_file, sample_rate, signal)
    
    print(f"Fichier audio généré: {output_file}")
    print(f"Durée: {duration} secondes")
    print(f"Taux d'échantillonnage: {sample_rate} Hz")
    print(f"Taille du fichier: {os.path.getsize(output_file)} octets")

def main():
    """Fonction principale."""
    # Chemin du fichier de sortie
    output_dir = Path(__file__).parent.parent / "assets" / "test_audio"
    output_file = output_dir / "test_sine_wave.wav"
    
    # Créer le répertoire de sortie s'il n'existe pas
    os.makedirs(output_dir, exist_ok=True)
    
    # Générer le fichier audio
    generate_test_audio(output_file)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
