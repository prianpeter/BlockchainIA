# blockchain/block.py
import time
import hashlib
from datetime import datetime
import json
# Import obligatoire du module C++ optimisé
try:
    import mine_module
except ImportError:
    raise ImportError(
        "\n[ERR] ERREUR : Module C++ de minage non trouvé !\n"
        "   Le minage nécessite le module C++ compilé pour des performances optimales.\n"
        "   Compilez-le avec : python setup.py build_ext --inplace\n"
        "   Assurez-vous d'avoir un compilateur C++ installé (Visual Studio sur Windows).\n"
    )

class Block:
    def __init__(self, index, transactions, previous_hash, nonce=0, timestamp_override=None, hash_override=None, miner=None):
        self.index = index
        self.timestamp = timestamp_override if timestamp_override else time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.miner = miner
        self.hash = hash_override if hash_override else self.calculate_hash()

    def calculate_hash(self):
        """Calcule le hash SHA-256 du bloc."""
        tx_compacts = [tx.compact() for tx in self.transactions]
        
        block_string = json.dumps({
            "index": self.index,
            "timestamp": int(self.timestamp), 
            "transactions": tx_compacts,
            "nonce": self.nonce,
            "previous_hash": self.previous_hash
        }, sort_keys=True).encode()
        
        return hashlib.sha256(block_string).hexdigest()

    def mine_block(self, difficulty=4):
        """Effectue le Proof-of-Work (PoW) avec le module C++ optimisé."""
        # Utilisation du module C++ optimisé (obligatoire)
        tx_compacts = [tx.compact() for tx in self.transactions]
        base = json.dumps({
            "index": self.index,
            "timestamp": int(self.timestamp), 
            "transactions": tx_compacts,
            "previous_hash": self.previous_hash
        }, sort_keys=True)
        
        nonce, hash_result = mine_module.mine_pow(base, difficulty)
        self.nonce = nonce
        self.hash = hash_result

    # NOUVELLE MÉTHODE POUR LA SAUVEGARDE
    def to_dict(self):
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions': [tx.to_dict() for tx in self.transactions],
            'previous_hash': self.previous_hash,
            'proof': self.nonce,
            'hash': self.hash,
            'miner': self.miner
        }

    def display_block(self):
        date_str = datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n┌── BLOC #{self.index}")
        print(f"│ Hash      : {self.hash}")
        print(f"│ Précédent : {self.previous_hash}")
        print(f"│ Mineur    : {self.miner}")
        print(f"│ Date      : {date_str}")
        print(f"│ Transactions ({len(self.transactions)}):")
        
        if not self.transactions:
            print("│    (Aucune transaction)")
        else:
            for i, tx in enumerate(self.transactions):
                # --- SÉCURITÉ ANTI-N/A ---
                # 1. On essaie de récupérer .id ou .hash
                tx_id = getattr(tx, 'id', getattr(tx, 'hash', None))
                
                # 2. Si c'est None ou "N/A", on le recalcule immédiatement
                if not tx_id or tx_id == "N/A":
                    raw_data = f"{tx.sender}{tx.receiver}{tx.amount}{tx.timestamp}"
                    tx_id = "0x" + hashlib.sha256(raw_data.encode()).hexdigest()
                
                # 3. On s'assure qu'il commence par 0x
                if not str(tx_id).startswith("0x"):
                    tx_id = f"0x{tx_id}"

                tx_time = datetime.fromtimestamp(tx.timestamp).strftime('%H:%M:%S')

                print(f"│    {i+1}. [{tx_time}] ID: {tx_id}")
                print(f"│       Expéditeur  : {tx.sender}")   
                print(f"│       Destinataire : {tx.receiver}") 
                print(f"│       Montant      : {tx.amount:.2f} €")
                print(f"│       " + "-"*45)
