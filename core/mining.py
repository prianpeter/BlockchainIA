"""
Logique de minage et génération de transactions AI
"""
import time
import random
from blockchain.block import Block


def prefill_ai_queue(blockchain, queue, peers, batch_size=4):
    """
    Génère des transactions via l'IA et les diffuse au réseau.
    
    Args:
        blockchain: Instance de la blockchain
        queue: Queue pour stocker les transactions générées
        peers: Set des peers réseau
        batch_size: Nombre de transactions par batch
    """
    import requests
    from ai.generator import generate_ai_transactions
    
    REQUESTS_AVAILABLE = True
    try:
        import requests
    except ImportError:
        REQUESTS_AVAILABLE = False
        print("[WARN] Module requests non disponible - diffusion désactivée")
    
    while True:
        current_time = time.time()
        
        txs = []
        try:
            txs = generate_ai_transactions(blockchain, n=batch_size)
        except Exception:
            wallet_ids = list(blockchain.wallets.keys())
            txs = []
            
            for _ in range(batch_size * 5): 
                if len(wallet_ids) < 2:
                     break
                s, r = random.sample(wallet_ids, 2)
                amt = random.randint(100, 1500) 
                random_offset = random.uniform(0, 60) 
                tx_time = current_time - random_offset
                tx = blockchain.create_transaction(s, r, amt, timestamp_override=tx_time) 
                if tx: 
                    txs.append(tx)
                if len(txs) >= batch_size:
                    break
            
        txs = [tx for tx in txs if tx is not None]
        if txs:
            txs_data_list = [tx.to_dict() for tx in txs]
            payload = {'transactions': txs_data_list}
            node_port = 5002  # Port par défaut
            all_peers = peers.union({f"http://127.0.0.1:{node_port}"})
            
            if not REQUESTS_AVAILABLE:
                continue

            for peer in all_peers:
                try:
                    url = f'{peer}/transactions/new'
                    requests.post(url, json=payload, timeout=3)
                except Exception:
                    pass
            
            time.sleep(1)
        else:
            time.sleep(5)


def auto_miner(blockchain, peers, ai_queue, transaction_pool_ids, auto_mining_flag, broadcast_fn, cleanup_fn, get_valid_txs_fn, base_reward=5.0, fee_per_tx=1.0):
    """
    Fonction qui mine automatiquement en arrière-plan.
    
    Args:
        blockchain: Instance de la blockchain
        peers: Set des peers réseau
        ai_queue: Queue de transactions
        transaction_pool_ids: Set des IDs de transactions en pool
        auto_mining_flag: Dictionnaire avec flag 'enabled' pour contrôler le minage
        broadcast_fn: Fonction pour diffuser les blocs
        cleanup_fn: Fonction pour nettoyer le pool
        get_valid_txs_fn: Fonction pour récupérer les TX valides
        base_reward: Récompense de base par bloc
        fee_per_tx: Frais par transaction
    """
    print("[AUTO-MINER] Mineur automatique demarre...")
    while True:
        # Attendre que l'auto-minage soit activé
        if not auto_mining_flag.get('enabled', False):
            time.sleep(2)
            continue
            
        # Synchronisation avant de miner
        if peers:
            blockchain.resolve_conflicts(peers)
            
        txs = get_valid_txs_fn(blockchain, ai_queue, transaction_pool_ids, batch_size=4)
        
        if len(txs) >= 4:
            print(f"\n[AUTO-MINER] [MINE] Tentative de minage d'un nouveau bloc ({len(txs)} tx)...")
            try:
                # 1. Création du bloc
                new_block = Block(len(blockchain.chain), txs, blockchain.chain[-1].hash)
                
                # 2. On définit qui est le mineur AVANT de calculer le hash
                new_block.miner = blockchain.miner_wallet
                
                # 3. Minage réel (difficulté basse pour ne pas bloquer le CPU)
                new_block.mine_block(difficulty=1)
                
                # 4. Ajout à la chaîne
                blockchain.add_block(new_block)
                
                # 5. Diffusion et nettoyage
                broadcast_fn(new_block, peers)
                cleanup_fn(txs, ai_queue, transaction_pool_ids, blockchain)
                
                print(f"[AUTO-MINER] [OK] Bloc {new_block.index} miné et diffusé !")
                
                # Tentative de synchro légère après minage
                blockchain.resolve_conflicts(peers)
                
            except Exception as e:
                print(f"[AUTO-MINER] [ERR] Erreur lors du minage auto : {e}")

        # Pause de 15 secondes pour laisser l'IA générer des transactions
        time.sleep(15)


def broadcast_block(block, peers):
    """
    Diffuse un bloc miné à tous les pairs du réseau.
    
    Args:
        block: Bloc à diffuser
        peers: Set des peers réseau
    """
    import requests
    
    block_data = {
        'index': block.index,
        'timestamp': block.timestamp,
        'transactions': [tx.to_dict() for tx in block.transactions],
        'proof': block.nonce,
        'previous_hash': block.previous_hash,
        'hash': block.hash
    }
    
    if hasattr(block, 'miner') and block.miner:
        block_data['miner'] = block.miner
    
    for peer in peers:
        try:
            requests.post(f'{peer}/block', json=block_data, timeout=2)
            print(f"[NET] Bloc diffusé au pair {peer}")
        except Exception as e:
            print(f"[ERR] Erreur de diffusion du bloc au pair {peer}: {e}")
