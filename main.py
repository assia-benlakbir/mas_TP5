"""
Script de test - Exécuter pour vérifier votre solution

Prérequis:
    pip install spade

Exécution:
    python main.py
"""

import spade
from exercices import main

if __name__ == "__main__":
    spade.run(main(), embedded_xmpp_server=True)
