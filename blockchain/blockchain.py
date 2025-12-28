# blockchain/blockchain.py
import random
try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    requests = None
    REQUESTS_AVAILABLE = False
import json
import os 
import time
from .block import Block
from .transaction import Transaction
from .fees_contract import mining_fee_contract
import datetime

# Chemin du fichier de sauvegarde
DATA_FILE = 'blockchain_data.json'

def gen_wallet_id():
    return "0x" + "".join(random.choice("0123456789abcdef") for _ in range(16))

class Blockchain:
    def __init__(self, initial_wallets=20, load_existing=True): 
        self.miner_wallet = None 
        self.failed_transactions = []
        self.internal_tx_history = []
        self.chain = []
        self.wallets = {}

        if load_existing and os.path.exists(DATA_FILE):
            print(f"Chargement de la chaine existante depuis {DATA_FILE}...")
            try:
                self.load_data()
                print(f"[OK] Chaine chargee. Taille : {len(self.chain)}")
            except Exception as e:
                print(f"[ERREUR] Erreur de chargement ({e}), creation d'une nouvelle chaine...")
                self.reset_blockchain(initial_wallets)
        else:
            self.reset_blockchain(initial_wallets)

    def reset_blockchain(self, initial_wallets):
        """Initialise une nouvelle blockchain à zéro."""
        self.chain = [self.create_genesis_block()]
        self.wallets = self.generate_wallets(initial_wallets)
        self.miner_wallet = gen_wallet_id()
        self.wallets[self.miner_wallet] = 50000 
        self.save_data()

    def create_genesis_block(self):
        """Crée le premier bloc (Genèse) de la chaîne."""
        GENESIS_HASH = "8c6d1d49e1f5a5e3c8801d9f0f9b1e941a5f4d1a04d3e8e19b486241b2e535a0"
        genesis_block = Block(
            index=0, 
            transactions=[], 
            previous_hash="0", 
            nonce=0, 
            timestamp_override=0, 
            hash_override=GENESIS_HASH,
            miner="GENESIS"
        )
        return genesis_block

    def generate_wallets(self, n):
        wallets = {}
        for _ in range(n):
            wallets[gen_wallet_id()] = 5000 
        return wallets

    # --- MÉTHODES DE SAUVEGARDE ET CHARGEMENT ---

    def to_dict(self):
        return {
            'chain': [block.to_dict() for block in self.chain],
            'failed_transactions': [tx.to_dict() for tx in self.failed_transactions],
            'wallets': self.wallets,
            'miner_wallet': self.miner_wallet,
            'internal_tx_history': self.internal_tx_history
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(initial_wallets=0, load_existing=False) 
        instance.chain = []
        for b_data in data['chain']:
            tx_objs = [
                Transaction(
                    tx['sender'], tx['receiver'], tx['amount'], 
                    tx['status'], tx.get('signature'), tx['timestamp']
                ) for tx in b_data['transactions']
            ]
            blk = Block(
                b_data['index'], tx_objs, b_data['previous_hash'], 
                b_data['proof'], b_data['timestamp'], b_data['hash'],
                miner=b_data.get('miner') # <--- RÉCUPÉRATION DU MINEUR
            )
            instance.chain.append(blk)
        
        instance.failed_transactions = [
            Transaction(tx['sender'], tx['receiver'], tx['amount'], tx['status'], tx.get('signature'), tx['timestamp']) 
            for tx in data['failed_transactions']
        ]
        instance.wallets = data['wallets']
        instance.miner_wallet = data['miner_wallet']
        instance.internal_tx_history = data['internal_tx_history']
        return instance

    def save_data(self):
        with open(DATA_FILE, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    def load_data(self):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            loaded = self.from_dict(data)
            self.chain = loaded.chain
            self.wallets = loaded.wallets
            self.miner_wallet = loaded.miner_wallet
            self.failed_transactions = loaded.failed_transactions
            self.internal_tx_history = loaded.internal_tx_history

    # --- LOGIQUE DE TRANSACTION ET MINAGE ---

    def add_block(self, block):
        # On s'assure que le bloc a bien l'ID du mineur local avant ajout
        if not block.miner:
            block.miner = self.miner_wallet
        self.chain.append(block)
        self.recalculate_wallets() # Recalcul pour les fees
        self.save_data()

    def create_transaction(self, sender, receiver, amount, timestamp_override=None):
        if sender not in self.wallets: self.wallets[sender] = 5000
        if receiver not in self.wallets: self.wallets[receiver] = 5000

        if self.wallets.get(sender, 0) < amount:
            tx = Transaction(sender, receiver, amount, status="failed", timestamp_override=timestamp_override)
            self.failed_transactions.append(tx)
            return None
        
        tx = Transaction(sender, receiver, amount, status="success", timestamp_override=timestamp_override)
        tx.sign(sender) 
        return tx

    def get_balance(self, wallet_id):
        return self.wallets.get(wallet_id, 0)

    def show_failed_transactions(self):
        print("\n=== TRANSACTIONS ÉCHOUÉES (POOL) ===")
        if not self.failed_transactions:
            print("Aucune transaction échouée.")
        else:
            for tx in self.failed_transactions:
                tx_time = datetime.datetime.fromtimestamp(getattr(tx, 'timestamp', time.time())).strftime('%d/%m/%Y %H:%M:%S')
                tx_id = getattr(tx, 'id', None) or getattr(tx, 'hash', 'N/A')
                print(f"[ERR] ID: {tx_id} | {tx_time} | {tx.sender} -> {tx.receiver} | {tx.amount:.2f} € | statut: {tx.status}")
        print("====================================\n")

    def get_history(self, wallet_id):
        # On recalcule avant de donner l'historique pour être à jour après une synchro
        self.recalculate_wallets()
        successes = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.sender == wallet_id or tx.receiver == wallet_id:
                    successes.append((block.index, tx))
        failures = [tx for tx in self.failed_transactions if tx.sender == wallet_id or tx.receiver == wallet_id]
        internal = [tx for tx in self.internal_tx_history if tx["sender"] == wallet_id or tx["receiver"] == wallet_id]
        return successes, failures, internal

    def display_chain(self):
        print("\n" + "="*30 + " [CHAIN] ÉTAT DE LA BLOCKCHAIN " + "="*30)
        
        for block in self.chain:
            print(f"\n┌── BLOC #{block.index}")
            print(f"│ Hash: {block.hash}")
            print(f"│ Précédent: {block.previous_hash}")
            print(f"│ Nonce: {block.nonce}")
            print(f"│ Mineur: {block.miner if hasattr(block, 'miner') else 'Système'}")
            print(f"│ Horodatage: {datetime.datetime.fromtimestamp(block.timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"│ Transactions ({len(block.transactions)}):")
            
            if not block.transactions:
                print("│    (Aucune transaction)")
            else:
                for i, tx in enumerate(block.transactions):
                    # On récupère l'ID de transaction (préférence pour .id puis .hash)
                    tx_id = getattr(tx, 'id', None) or getattr(tx, 'hash', None)
                    if not tx_id:
                        tx_id = 'N/A'

                    # On récupère le temps de la transaction s'il existe
                    tx_time = ""
                    if hasattr(tx, 'timestamp'):
                        tx_time = f" [{datetime.datetime.fromtimestamp(tx.timestamp).strftime('%H:%M:%S')}]"

                    # Affichage sécurisé (couper si trop long)
                    display_id = tx_id[:16] + '...' if tx_id != 'N/A' else 'N/A'

                    print(f"│    {i+1}.{tx_time} ID: {display_id}")
                    print(f"│       Expéditeur : {tx.sender}")
                    print(f"│       Destinataire: {tx.receiver}")
                    print(f"│       Montant     : {tx.amount:.2f} €")
                    print(f"│       --------------------------------------")
            print(f"└" + "─"*50)

    def recalculate_wallets(self):
        """Source de vérité absolue pour synchroniser les soldes Mac/Windows."""
        # 1. Identifier tous les mineurs en parcourant la chaîne
        all_miners = set()
        for block in self.chain:
            if block.index == 0: continue
            if block.miner:
                all_miners.add(block.miner)
        
        # 2. RECONSTRUIRE le dictionnaire wallets à partir de zéro
        # Ne garder QUE les wallets qui apparaissent dans la blockchain
        all_wallets_in_chain = set()
        
        # Collecter tous les wallets utilisés
        for block in self.chain:
            if block.index == 0: continue
            if block.miner:
                all_wallets_in_chain.add(block.miner)
            for tx in block.transactions:
                all_wallets_in_chain.add(tx.sender)
                all_wallets_in_chain.add(tx.receiver)
        
        # Créer un nouveau dictionnaire avec UNIQUEMENT les wallets utilisés
        self.wallets = {}
        for wallet_id in all_wallets_in_chain:
            if wallet_id in all_miners:
                self.wallets[wallet_id] = 50000
            else:
                self.wallets[wallet_id] = 5000
        
        self.internal_tx_history = []

        for block in self.chain:
            if block.index == 0: continue
            
            block_miner = block.miner
            if not block_miner: continue

            for tx in block.transactions:
                # 1. Transfert du montant
                self.wallets[tx.sender] -= tx.amount
                self.wallets[tx.receiver] += tx.amount
                
                # 2. Frais (Fee) attribués au mineur du bloc
                fee = 1.0
                self.wallets[tx.sender] -= fee
                self.wallets[block_miner] += fee
                
                self.internal_tx_history.append({
                    "sender": tx.sender, "receiver": block_miner,
                    "amount": fee, "type": "fee", "timestamp": tx.timestamp
                })

    # --- LOGIQUE RÉSEAU ET CONSENSUS ---

    def is_valid_chain(self, chain):
        if not chain or chain[0].index != 0: return False
        for i in range(1, len(chain)):
            if chain[i].previous_hash != chain[i-1].hash: return False
        return True

    def resolve_conflicts(self, peers):
        new_chain = None
        max_length = len(self.chain)
        
        if not peers:
            print("[WARN] Aucun pair enregistré. Utilisez l'option 6.")
            return False

        if not REQUESTS_AVAILABLE:
            print("[WARN] Module 'requests' introuvable — résolution de conflits réseau désactivée.")
            return False

        for peer in peers:
            print(f"🔍 Tentative de connexion à : {peer}...") # Ajoute ça pour débugger
            try:
                # Sécurité pour l'URL
                url = peer if peer.startswith('http') else f'http://{peer}'
                response = requests.get(f'{url}/chain', timeout=3)
                
                if response.status_code == 200:
                    data = response.json()
                    length = data['length']
                    chain_data = data['chain']

                    if length > max_length:
                        temp_chain = []
                        for b_data in chain_data:
                            tx_objs = [
                                Transaction(tx['sender'], tx['receiver'], tx['amount'], 
                                            tx['status'], tx.get('signature'), tx['timestamp']) 
                                for tx in b_data['transactions']
                            ]
                            blk = Block(
                                b_data['index'], tx_objs, b_data['previous_hash'], 
                                b_data['proof'], b_data['timestamp'], b_data['hash'],
                                miner=b_data.get('miner') # <--- RÉCUPÉRATION DU MINEUR RÉSEAU
                            )
                            temp_chain.append(blk)
                        
                        if self.is_valid_chain(temp_chain):
                            max_length = length
                            new_chain = temp_chain
            except Exception:
                continue

        if new_chain:
            self.chain = new_chain
            self.recalculate_wallets()
            self.save_data()
            print(f"[OK] Synchronisation réussie ! Nouvelle taille : {max_length}")
            return True
        return False

    def to_json_chain(self):
        return [block.to_dict() for block in self.chain]