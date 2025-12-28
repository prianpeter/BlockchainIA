"""
Point d'entrée principal de l'application blockchain
Version refactorisée - Architecture modulaire
"""
import os
import signal
import time
import random
import threading
from queue import Queue
from flask import Flask

# Imports locaux
from blockchain.blockchain import Blockchain
from blockchain.block import Block
from blockchain.transaction import Transaction
from blockchain.fees_contract import mining_fee_contract
from core.utils import (get_valid_txs, cleanup_transaction_pool, display_wallet_history)
from core.mining import prefill_ai_queue, auto_miner, broadcast_block
from core.routes import init_routes

# ============================================================
# CONFIGURATION GLOBALE
# ============================================================

NODE_PORT = int(os.getenv('PORT', '5003'))
NODE_ID = f"node_{NODE_PORT}"
ZEROTIER_NETWORK_ID = os.getenv('ZEROTIER_NETWORK_ID', '12ac4a1e71a03912')

FEE_PER_TX = 1.0
BASE_BLOCK_REWARD = 5.0

# Sets et queues globaux
PEERS = set()
ai_queue = Queue()
transaction_pool_ids = set()
auto_mining_flag = {'enabled': False}

# ============================================================
# GESTION DES PAIRS
# ============================================================

def load_peers():
    """Charge les pairs depuis peers.json"""
    import json
    try:
        with open('peers.json', 'r') as f:
            data = json.load(f)
            return set(data.get('peers', []))
    except FileNotFoundError:
        return set()

def save_peers():
    """Sauvegarde les pairs dans peers.json"""
    import json
    with open('peers.json', 'w') as f:
        json.dump({'peers': list(PEERS)}, f, indent=2)

# ============================================================
# INITIALISATION BLOCKCHAIN
# ============================================================

print("\n[OK] Chargement de la blockchain...")
bc = Blockchain()
bc.load_data()

# Initialisation de la base de données SQLite
try:
    from core import db
    db.init_db()
    db.sync_from_blockchain(bc)
    print("[OK] DB initialisee et synchronisee.")
except Exception as e:
    print(f"[WARN] Erreur initialisation DB : {e}")

# Charger les pairs
PEERS = load_peers()

# ============================================================
# APPLICATION FLASK
# ============================================================

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret')

# Enregistrer toutes les routes
init_routes(app, bc, PEERS, NODE_ID, NODE_PORT, BASE_BLOCK_REWARD, FEE_PER_TX, 
           ai_queue, transaction_pool_ids)

# ============================================================
# GESTIONNAIRES DE SAUVEGARDE
# ============================================================

def save_on_exit(sig, frame):
    """Sauvegarde au CTRL+C"""
    print("\n[OK] Signal d'arrêt reçu. Sauvegarde en cours...")
    bc.save_data()
    save_peers()
    print("[OK] Données sauvegardées. Arrêt propre.")
    os._exit(0)

def auto_save_thread(interval=300):
    """Thread de sauvegarde automatique toutes les 5 minutes"""
    while True:
        time.sleep(interval)
        try:
            bc.save_data()
            save_peers()
            print(f"[OK] Sauvegarde auto (toutes les {interval}s)")
        except Exception:
            pass

# ============================================================
# MENU INTERACTIF
# ============================================================

def run_menu():
    """Menu interactif dans le terminal"""
    while True:
        print("\n" + "="*20 + " MENU BLOCKCHAIN " + "="*20)
        print("1. Miner manuellement (Interactif)")
        print("2. Afficher la blockchain")
        print("3. Afficher les transactions échouées")
        print("4. Consulter l'historique & solde d'un portefeuille")
        print("5. Enregistrer un Pair (Nœud)")
        print("6. Synchroniser la Chaîne (Consensus)") 
        print("0. Quitter")
        
        choix = input("\nVotre choix : ").strip()

        if choix == "0":
            print("Arrêt du processus...")
            os._exit(0)
            
        elif choix == "1":
            try:
                nb = int(input("Combien de blocs miner ? ").strip())
            except ValueError:
                nb = 1
            
            try:
                difficulty = int(input("Choisis la difficulté du PoW (ex: 0, 1, 2) : ").strip())
            except ValueError:
                difficulty = 0

            mined_blocks = []
            print(f"[MINE] Lancement du minage de {nb} bloc(s) avec difficulté {difficulty}...")

            for i in range(nb):
                txs = get_valid_txs(bc, ai_queue, transaction_pool_ids, batch_size=4) 

                if not txs:
                    wallet_ids = list(bc.wallets.keys())
                    if len(wallet_ids) >= 2:
                        for _ in range(4):
                            s, r = random.sample(wallet_ids, 2)
                            tx = bc.create_transaction(s, r, random.randint(50, 1000))
                            if tx: 
                                txs.append(tx)

                if not txs:
                    print(f"[WARN] Bloc {i+1}/{nb}: Impossible de générer des transactions.")
                    continue 

                new_block = Block(len(bc.chain), txs, bc.chain[-1].hash)
                new_block.miner = bc.miner_wallet

                for tx in txs:
                    mining_fee_contract(None, bc, tx.sender, tx.amount)

                start = time.time()
                new_block.mine_block(difficulty)
                end = time.time()
                mining_time = end - start

                bc.add_block(new_block)

                try:
                    from core.db import save_block, upsert_wallets, save_internal_txs
                    reward_val = BASE_BLOCK_REWARD + len(txs) * FEE_PER_TX
                    save_block(new_block, reward=reward_val)
                    upsert_wallets(bc.wallets)
                    save_internal_txs(bc.internal_tx_history)
                except Exception:
                    pass
                
                broadcast_block(new_block, PEERS) 
                cleanup_transaction_pool(txs, ai_queue, transaction_pool_ids, bc)
                bc.save_data() 

                mined_blocks.append((new_block, mining_time))
                print(f" [OK] Bloc {new_block.index} miné en {mining_time:.4f}s")

            print("\n=== RÉSUMÉ DU MINAGE MANUEL ===")
            for blk, t in mined_blocks:
                print(f" Bloc {blk.index} | TX: {len(blk.transactions)} | Hash: {blk.hash[:12]}... | Temps: {t:.4f}s")
            
            print("\n[SYNC] Résolution des conflits réseau...")
            bc.resolve_conflicts(PEERS) 

        elif choix == "2":
            bc.display_chain()

        elif choix == "3":
            bc.show_failed_transactions()

        elif choix == "4":
            pid = input("Entrez l'ID du portefeuille (ex: 0x...) : ").strip()
            display_wallet_history(bc, pid)
            
        elif choix == "5":
            address = input("Entrez l'adresse du pair (ex: http://192.168.1.10:5003) : ").strip()
            if address:
                if not address.startswith("http"):
                    address = "http://" + address
                PEERS.add(address)
                print(f"[OK] Pair ajouté : {address}")
            else:
                print("[ERR] Adresse invalide.")
        
        elif choix == "6":
            print("\n[SYNC] Démarrage de la synchronisation forcée...")
            bc.resolve_conflicts(PEERS)
            
        else:
            print("[ERR] Choix invalide.")

# ============================================================
# DÉMARRAGE PRINCIPAL
# ============================================================

if __name__ == '__main__':
    signal.signal(signal.SIGINT, save_on_exit) 
    
    # Vérifier que le module C++ est compilé (OBLIGATOIRE)
    try:
        import mine_module
        print("\n[C++] Module de minage C++ activé - Performance optimale !")
    except ImportError:
        print("\n" + "="*70)
        print("[ERR] ERREUR CRITIQUE : Module C++ de minage non compilé !")
        print("="*70)
        print("\nLe minage nécessite le module C++ pour des performances optimales.")
        print("   Compilez-le maintenant avec la commande suivante :\n")
        print("   → python setup.py build_ext --inplace\n")
        print("[WARN] Assurez-vous d'avoir un compilateur C++ installé :")
        print("   • Windows : Visual Studio Build Tools")
        print("   • Linux   : gcc (apt install build-essential)")
        print("   • Mac     : Xcode Command Line Tools\n")
        print("="*70)
        input("\nAppuyez sur Entrée pour quitter...")
        exit(1)
    
    # Question au démarrage : se connecter à une blockchain existante ?
    print("\n" + "="*60)
    print("[NET] Voulez-vous vous connecter à une blockchain existante ?")
    print("="*60)
    choice = input("(o)ui / (n)on : ").strip().lower()
    
    if choice == 'o':
        print("\n[NET] Connexion à un pair...")
        peer_address = input("Entrez l'adresse du pair (ex: http://172.22.100.50:5002) : ").strip()
        
        if not peer_address.startswith('http'):
            peer_address = 'http://' + peer_address
        
        PEERS.add(peer_address)
        print(f"[OK] Pair ajouté : {peer_address}")
        
        print("[SYNC] Synchronisation avec le réseau...")
        replaced = bc.resolve_conflicts(PEERS)
        if replaced:
            print("[OK] Blockchain synchronisée !")
        else:
            print("[OK] Blockchain locale déjà à jour.")
    else:
        print("[OK] Démarrage en mode autonome.")
    
    # Question : activer l'auto-miner ?
    print("\n" + "="*60)
    print("[MINE] Activer le mineur automatique ?")
    print("="*60)
    auto_choice = input("(o)ui / (n)on : ").strip().lower()
    
    if auto_choice == 'o':
        auto_mining_flag['enabled'] = True
        print("[OK] Auto-miner activé !")
    else:
        print("[OK] Auto-miner désactivé. Utilisez le menu pour miner manuellement.")
    
    # Démarrage des threads
    print("\n[OK] Démarrage des threads...")
    
    # Thread 1: Génération de transactions IA
    ai_thread = threading.Thread(
        target=prefill_ai_queue, 
        args=(bc, ai_queue, PEERS), 
        daemon=True
    )
    ai_thread.start()
    print("[OK] Thread AI démarre...")
    
    # Thread 2: Sauvegarde automatique
    save_thread = threading.Thread(target=auto_save_thread, daemon=True)
    save_thread.start()
    print("[OK] Thread sauvegarde auto démarre...")
    
    # Thread 3: Auto-miner
    miner_thread = threading.Thread(
        target=auto_miner,
        args=(bc, PEERS, ai_queue, transaction_pool_ids, auto_mining_flag, 
              broadcast_block, cleanup_transaction_pool, get_valid_txs, 
              BASE_BLOCK_REWARD, FEE_PER_TX),
        daemon=True
    )
    miner_thread.start()
    print("[OK] Thread auto-miner démarre...")
    
    # Thread 4: Menu interactif
    menu_thread = threading.Thread(target=run_menu, daemon=True)
    menu_thread.start()
    print("[OK] Thread menu interactif démarre...")
    
    # Démarrage du serveur Flask
    print("\n" + "="*70)
    print(f"[OK] Serveur Flask démarre sur http://127.0.0.1:{NODE_PORT}")
    print(f"[OK] Node ID: {NODE_ID}")
    print(f"[OK] Portefeuille mineur: {bc.miner_wallet}")
    print("="*70 + "\n")
    
    try:
        app.run(host='0.0.0.0', port=NODE_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        save_on_exit(None, None)
