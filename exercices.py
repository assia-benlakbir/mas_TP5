"""
TP Bonus : Système de Livraison avec SPADE
À COMPLÉTER

Prérequis:
    pip install spade
    
Exécution:
    python main.py
"""

import spade
import asyncio
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message

# Pour éviter les warning logs
import logging

# Baisser le niveau de verbosité
logging.getLogger("spade").setLevel(logging.CRITICAL)
logging.getLogger("pyjabber").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


# =============================================================================
# PARTIE 1 : Agent Livreur
# =============================================================================

class LivreurAgent(Agent):
    """
    Agent livreur qui répond aux appels d'offres.
    
    Attributs:
        tarif: prix par km
        position: tuple (x, y)
        disponible: True/False
    """
    
    def __init__(self, jid, password, tarif, position, disponible=True):
        super().__init__(jid, password)
        self.tarif = tarif
        self.position = position
        self.disponible = disponible
    
    def calculer_distance(self, destination):
        """Distance Manhattan vers la destination."""
        return abs(self.position[0] - destination[0]) + abs(self.position[1] - destination[1])
    
    class RecevoirCFP(CyclicBehaviour):
        """Comportement pour recevoir et traiter les CFP."""
        
        async def run(self):
            msg = await self.receive(timeout=5)
            if msg:
                performative = msg.get_metadata("performative")
                
                if performative == "cfp":
                    # Extraire la destination
                    if msg.body.startswith("livraison:"):
                        dest_str = msg.body.split(":")[1]
                        destination = tuple(map(int, dest_str.strip("()").split(",")))
                    else:
                        destination = eval(msg.body)  # Fallback si format différent

                    if self.agent.disponible:
                        distance = self.agent.calculer_distance(destination)
                        cout = distance * self.agent.tarif
        
                        reponse = msg.make_reply()
                        reponse.set_metadata("performative", "propose")
                        reponse.body = f"cout:{cout}"
                        await self.send(reponse)
                        print(f"[{self.agent.jid}] Proposition: {cout}€")
                    else:
                        reponse = msg.make_reply()
                        reponse.set_metadata("performative", "refuse")
                        reponse.body = "indisponible"
                        await self.send(reponse)
                        print(f"[{self.agent.jid}] Refusé (indisponible)")
                
                elif performative == "accept-proposal":
                    print(f"[{self.agent.jid}] Livraison acceptée!")
    
                    reponse = msg.make_reply()
                    reponse.set_metadata("performative", "inform")
                    reponse.body = "done"
                    await self.send(reponse)
                    
                    # Marquer le livreur comme indisponible pendant la livraison
                    self.agent.disponible = False
                
                elif performative == "reject-proposal":
                    # Afficher "Offre refusée"
                    print(f"[{self.agent.jid}] Offre refusée")
    
    async def setup(self):
        print(f"🚚 {self.jid} démarré (tarif={self.tarif}, position={self.position})")
        self.add_behaviour(self.RecevoirCFP())


# =============================================================================
# PARTIE 2 : Agent Gestionnaire
# =============================================================================

class GestionnaireAgent(Agent):
    """
    Agent gestionnaire qui coordonne les livraisons via Contract Net.
    """
    
    def __init__(self, jid, password, livreurs_jids):
        super().__init__(jid, password)
        self.livreurs_jids = livreurs_jids  # Liste des JIDs des livreurs
        self.propositions = []
        self.destination = None
    
    class LancerAppelOffres(OneShotBehaviour):
        """Comportement pour lancer un appel d'offres."""
        
        async def on_start(self):
            self.agent.propositions = []
        
        async def run(self):
            destination = self.agent.destination
            print(f"\n📢 Lancement appel d'offres pour livraison à {destination}")
            
            for livreur_jid in self.agent.livreurs_jids:
                msg = Message(to=livreur_jid)
                msg.set_metadata("performative", "cfp")
                msg.body = f"livraison:{destination}"
                await self.send(msg)
                print(f"  CFP envoyé à {livreur_jid}")

            # Attendre les réponses
            await asyncio.sleep(2)
    
    class CollecterPropositions(CyclicBehaviour):
        """Comportement pour collecter les propositions."""
        
        async def run(self):
            msg = await self.receive(timeout=3)
            if msg:
                performative = msg.get_metadata("performative")
                
                if performative == "propose":
                    try:
                        # Extraire le coût du message (format: "cout:XX")
                        cout = float(msg.body.split(":")[1])
                    
                        # Ajouter la proposition à la liste
                        proposition = {
                            'livreur': str(msg.sender),
                            'cout': cout
                        }
                        self.agent.propositions.append(proposition)
                    
                        # Afficher la proposition
                        print(f"  ✓ Proposition reçue de {msg.sender}: {cout}€")
                    
                    except (ValueError, IndexError):
                        print(f"  ✗ Format de proposition invalide de {msg.sender}: {msg.body}")
                
                elif performative == "refuse":
                    print(f"  ❌ {msg.sender} a refusé")
                
                elif performative == "inform":
                    if msg.body == "done":
                        print(f"  ✅ Livraison confirmée par {msg.sender}")
    
    class SelectionnerMeilleur(OneShotBehaviour):
        """Comportement pour sélectionner la meilleure offre."""
        
        async def run(self):
            await asyncio.sleep(3)  # Attendre les propositions
            
            print(f"\n🔍 Évaluation des {len(self.agent.propositions)} propositions...")
            
            if not self.agent.propositions:
                print("  Aucune proposition reçue!")
                return
            
            meilleure_proposition = min(self.agent.propositions, key=lambda prop: prop["cout"])
        
            # Pour chaque proposition:
            for proposition in self.agent.propositions:
                if proposition["livreur"] == meilleure_proposition["livreur"]:
                    # Si c'est le gagnant: envoyer "accept-proposal"
                    msg_accept = Message(to=proposition["livreur"])
                    msg_accept.set_metadata("performative", "accept-proposal")
                    await self.send(msg_accept)
                    print(f"  ✓ Acceptation envoyée à {proposition['livreur']} (coût: {proposition['cout']}€)")
                else:
                    # Sinon: envoyer "reject-proposal"
                    msg_reject = Message(to=proposition["livreur"])
                    msg_reject.set_metadata("performative", "reject-proposal")
                    await self.send(msg_reject)
                    print(f"  ✗ Rejet envoyé à {proposition['livreur']} (coût: {proposition['cout']}€)")
        
            # Afficher le gagnant
            print(f"\n GAGNANT: {meilleure_proposition['livreur']}")
            print(f"   Coût: {meilleure_proposition['cout']}€")
            print(f"   Nombre total de propositions: {len(self.agent.propositions)}")
    
    async def setup(self):
        print(f"📋 {self.jid} démarré")
        self.add_behaviour(self.CollecterPropositions())
    
    def lancer_livraison(self, destination):
        """Lancer une livraison vers une destination."""
        self.destination = destination
        self.add_behaviour(self.LancerAppelOffres())
        # La sélection se fait après la collecte


# =============================================================================
# PARTIE 3 : Fonction principale
# =============================================================================

async def main():
    """Lancer la simulation."""
    print("=" * 60)
    print("🚚 SIMULATION SYSTÈME DE LIVRAISON SPADE")
    print("=" * 60)
    
    # Créer 3 agents livreurs
    livreur_a = LivreurAgent("livreur_assia@localhost", "password", 
                           tarif=2.0, position=(0, 0), disponible=True)
    livreur_b = LivreurAgent("livreur_aya@localhost", "password", 
                           tarif=1.5, position=(5, 5), disponible=True)
    livreur_c = LivreurAgent("livreur_hiba@localhost", "password", 
                           tarif=1.0, position=(10, 0), disponible=False)

    # Créer l'agent gestionnaire
    livreurs_jids = ["livreur_assia@localhost", "livreur_aya@localhost", "livreur_hiba@localhost"]
    gestionnaire = GestionnaireAgent("gestionnaire@localhost", "password", livreurs_jids)

    # Démarrer tous les agents
    await livreur_a.start()
    await livreur_b.start()
    await livreur_c.start()
    await gestionnaire.start()
    
    print("\n" + "=" * 60)
    print("🚀 AGENTS DÉMARRÉS")
    print("=" * 60)
    print(f"Gestionnaire: {gestionnaire.jid}")
    print(f"Livreur A: {livreur_a.jid} (tarif={livreur_a.tarif}, position={livreur_a.position})")
    print(f"Livreur B: {livreur_b.jid} (tarif={livreur_b.tarif}, position={livreur_b.position})")
    print(f"Livreur C: {livreur_c.jid} (tarif={livreur_c.tarif}, position={livreur_c.position})")
    print("=" * 60)
    
    # Attendre un peu puis lancer une livraison
    await asyncio.sleep(2)
    
    print("\n" + "=" * 60)
    print("📦 LANCEMENT D'UNE LIVRAISON VERS (3, 4)")
    print("=" * 60)
    
    # Lancer la livraison
    gestionnaire.lancer_livraison((3, 4))
    
    # Attendre que l'appel d'offres se termine
    await asyncio.sleep(3)
    
    # Lancer la sélection du meilleur
    gestionnaire.add_behaviour(gestionnaire.SelectionnerMeilleur())
    
    # Attendre la fin
    await asyncio.sleep(5)
    
    # Arrêter tous les agents
    print("\n" + "=" * 60)
    print("🛑 ARRÊT DES AGENTS")
    print("=" * 60)
    await livreur_a.stop()
    await livreur_b.stop()
    await livreur_c.stop()
    await gestionnaire.stop()


if __name__ == "__main__":
    # embedded_xmpp_server=True lance automatiquement le serveur XMPP
    spade.run(main(), embedded_xmpp_server=True)
