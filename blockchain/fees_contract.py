import time
from .transaction import Transaction # Import local de la classe Transaction

class SmartContract:
    """
    Classe de base pour simuler un Smart Contract sur la blockchain.
    """
    def __init__(self, owner, code, name="Contract"):
        self.owner = owner          # L'ID du wallet qui a déployé le contrat
        self.code = code            # La fonction Python qui définit la logique du contrat
        self.state = {}             # L'état interne persistant du contrat (ses données)
        self.name = name

    def execute(self, blockchain, sender, **kwargs):
        """
        Exécute la logique du contrat (self.code).
        Capture les erreurs d'exécution pour éviter de crasher le réseau.
        """
        try:
            # Passe le contrat lui-même, la blockchain, l'émetteur, et les arguments additionnels
            return self.code(self, blockchain, sender, **kwargs)
        except Exception as e:
            print(f"[WARN] Erreur lors de l'exécution du contrat {self.name}: {e}")
            return None


def mining_fee_contract(contract, blockchain, sender, amount):
    """
    Fonction de logique : Prélève des frais sur la transaction et les envoie au mineur.

    Cette fonction est le "code" exécuté par une instance de SmartContract.
    """
    fee_percent = 0.001  # Taux de frais : 0.1%
    fee = max(1, int(amount * fee_percent))  # Frais minimum de 1 unité
    miner_wallet = blockchain.miner_wallet

    # 1. Vérification des fonds pour les frais
    if blockchain.wallets.get(sender, 0) >= fee:
        # Initialisation du portefeuille du mineur si nécessaire
        if miner_wallet not in blockchain.wallets:
            blockchain.wallets[miner_wallet] = 0

        # 2. Application du mouvement des frais
        blockchain.wallets[sender] -= fee
        blockchain.wallets[miner_wallet] += fee

        # 3. Enregistrement de la transaction de frais (transaction interne)
        blockchain.internal_tx_history.append({
            "sender": sender,
            "receiver": miner_wallet,
            "amount": fee,
            "timestamp": time.time(),
            "label": f"Contract fee received from {sender}" # Étiquette pour l'historique
        })
        return True

    # Si l'émetteur n'a même pas les fonds pour les frais, on retourne False
    return False