"""
Utilitaires généraux pour la blockchain
Fonctions pures sans dépendances circulaires
"""
import time
import hashlib
from datetime import datetime


def get_valid_txs(bc, tx_pool, tx_pool_ids, batch_size=4):
    """
    Récupère des transactions valides depuis la queue AI ou génère des fallback.
    
    Args:
        bc: Instance de blockchain
        tx_pool: Queue contenant les transactions (ai_queue)
        tx_pool_ids: Set des IDs de transactions en pool
        batch_size: Nombre de transactions à récupérer
        
    Returns:
        Liste de transactions valides
    """
    txs = []
    
    # 1. Tenter d'obtenir des TX de la queue (AI thread)
    try:
        txs = tx_pool.get(timeout=1) 
    except Exception:
        pass
        
    # 2. Fallback local garanti si la queue était vide ou insuffisante
    if not txs or len(txs) < batch_size:
        import random
        wallet_ids = list(bc.wallets.keys())
        txs = []
        current_time = time.time()
        
        for _ in range(batch_size * 10): 
            if len(wallet_ids) < 2:
                break
                
            s, r = random.sample(wallet_ids, 2)
            amt = random.randint(100, 1500) 
            
            random_offset = random.uniform(0, 60) 
            tx_time = current_time - random_offset
            
            tx = bc.create_transaction(s, r, amt, timestamp_override=tx_time) 
            
            if tx:
                txs.append(tx)
            
            if len(txs) >= batch_size:
                break

    temp_wallets = bc.wallets.copy()
    
    valid_txs = []
    for tx in txs:
        if not tx.is_signature_valid(tx.sender):
            print(f"[ERR] Rejet de TX {tx.id[:12]}...: Signature invalide.")
            tx.status = "failed (signature)"
            bc.failed_transactions.append(tx)
            if tx.id in tx_pool_ids:
                tx_pool_ids.remove(tx.id) 
            continue 

        if temp_wallets.get(tx.sender, 0) >= tx.amount: 
            valid_txs.append(tx)
            temp_wallets[tx.sender] = temp_wallets.get(tx.sender, 0) - tx.amount
            temp_wallets[tx.receiver] = temp_wallets.get(tx.receiver, 0) + tx.amount 
        else:
            print(f"[ERR] Rejet de TX {tx.id[:12]}...: Fonds insuffisants dans l'état courant.")
            tx.status = "failed (funds)"
            bc.failed_transactions.append(tx)
            
        if tx.id in tx_pool_ids:
            tx_pool_ids.remove(tx.id) 
            
    return valid_txs[:batch_size]


def cleanup_transaction_pool(confirmed_txs, tx_pool, tx_pool_ids, bc):
    """
    Nettoie le pool de transactions après confirmation d'un bloc.
    
    Args:
        confirmed_txs: Liste des transactions confirmées
        tx_pool: Queue de transactions (ai_queue)
        tx_pool_ids: Set des IDs de transactions
        bc: Instance blockchain
    """
    temp_list = []
    while not tx_pool.empty():
        tx_list = tx_pool.get() 
        temp_list.extend(tx_list)
        
    confirmed_ids = {tx.id for tx in confirmed_txs}
    unconfirmed_txs = [tx for tx in temp_list if tx.id not in confirmed_ids]
    
    batch_size = 4
    for i in range(0, len(unconfirmed_txs), batch_size):
        tx_pool.put(unconfirmed_txs[i:i + batch_size])
    
    tx_pool_ids.clear()
    tx_pool_ids.update({tx.id for tx in unconfirmed_txs})

    bc.failed_transactions = [
        tx for tx in bc.failed_transactions if tx.id not in confirmed_ids
    ]
    
    print(f"[CLEAN] Nettoyage termine. {len(confirmed_ids)} TX confirmees retirees des pools.")


def find_transaction(tx_hash, blockchain):
    """
    Trouve une transaction dans la blockchain par son hash.
    
    Args:
        tx_hash: Hash de la transaction à rechercher
        blockchain: Instance de la blockchain
        
    Returns:
        Tuple (transaction, block_index) ou (None, None)
    """
    for block in blockchain.chain:
        for tx in block.transactions:
            if hasattr(tx, 'id') and tx.id == tx_hash:
                return tx, block.index
            # Fallback: calculer le hash si pas d'ID
            raw_data = f"{tx.sender}{tx.receiver}{tx.amount}{tx.timestamp}"
            calculated_hash = "0x" + hashlib.sha256(raw_data.encode()).hexdigest()
            if calculated_hash == tx_hash:
                return tx, block.index
    return None, None


def get_latest_transactions(blockchain, limit=10):
    """
    Récupère les N dernières transactions de la blockchain.
    
    Args:
        blockchain: Instance de la blockchain
        limit: Nombre maximum de transactions à retourner
        
    Returns:
        Liste de dictionnaires contenant tx, block_index et timestamp
    """
    txs = []
    for block in reversed(blockchain.chain):
        for tx in block.transactions:
            txs.append({
                'tx': tx,
                'block_index': block.index,
                'time': block.timestamp
            })
            if len(txs) >= limit:
                return txs
    return txs


def get_all_transactions(blockchain):
    """
    Récupère toutes les transactions de la blockchain.
    
    Args:
        blockchain: Instance de la blockchain
        
    Returns:
        Liste de dictionnaires contenant tx, block_index et timestamp
    """
    txs = []
    for block in reversed(blockchain.chain):
        for tx in block.transactions:
            txs.append({
                'tx': tx,
                'block_index': block.index,
                'time': block.timestamp
            })
    return txs


def display_wallet_history(bc, wallet_id):
    """
    Affiche l'historique complet d'un portefeuille dans le terminal.
    
    Args:
        bc: Instance de la blockchain
        wallet_id: Adresse du portefeuille
    """
    if wallet_id not in bc.wallets:
        print(f"\n[ERR] Portefeuille non trouvé : {wallet_id}")
        return

    balance = bc.get_balance(wallet_id)
    successes, failures, internal = bc.get_history(wallet_id)

    print(f"\n" + "="*90)
    print(f" SOLDE : {balance:.2f} €  |  WALLET : {wallet_id}")
    print("="*90)

    print("\n--- HISTORIQUE DES TRANSACTIONS ---")
    if successes:
        for block_index, tx in successes:
            if hasattr(tx, 'id') and tx.id:
                tx_id = tx.id
            else:
                raw_data = f"{tx.sender}{tx.receiver}{tx.amount}{tx.timestamp}"
                tx_id = "0x" + hashlib.sha256(raw_data.encode()).hexdigest()

            date_str = datetime.fromtimestamp(tx.timestamp).strftime('%d/%m/%Y %H:%M:%S')
            print(f" {tx_id} : {tx.sender} -> {tx.receiver} | {tx.amount:.2f} € | {date_str}")
    else:
        print(" (Aucune transaction trouvée)")

    print("\n--- FRAIS ET RÉCOMPENSES ---")
    if internal:
        for tx in internal:
            direction = "REÇU" if tx["receiver"] == wallet_id else "PAYÉ"
            sign = "+" if direction == "REÇU" else "-"
            date_int = datetime.fromtimestamp(tx.get("timestamp", time.time())).strftime('%H:%M:%S')
            label = tx.get('label') or tx.get('message') or "Frais"
            print(f" [{date_int}] {label} : {sign}{tx['amount']:.2f} € ({direction})")

    print("\n--- TRANSACTIONS ÉCHOUÉES (POOL) ---")
    if failures:
        for tx in failures:
            date_str = datetime.fromtimestamp(getattr(tx, 'timestamp', time.time())).strftime('%d/%m/%Y %H:%M:%S')
            tx_id = getattr(tx, 'id', None) or getattr(tx, 'hash', 'N/A')
            print(f" {tx_id} | {date_str} | {tx.sender} -> {tx.receiver} | {tx.amount:.2f} € | statut: {tx.status}")
    else:
        print(" (aucune transaction échouée)")

    print("\n" + "="*90)


def calculate_hashrate(blockchain):
    """
    Calcule le hashrate moyen de la blockchain.
    
    Args:
        blockchain: Instance de la blockchain
        
    Returns:
        float: Hashrate en hash/s
    """
    if len(blockchain.chain) < 2:
        return 0.0
    
    recent_blocks = blockchain.chain[-10:] if len(blockchain.chain) > 10 else blockchain.chain[1:]
    
    total_difficulty = 0
    total_time = 0
    
    for i in range(1, len(recent_blocks)):
        block = recent_blocks[i]
        prev_block = recent_blocks[i-1]
        
        time_diff = block.timestamp - prev_block.timestamp
        if time_diff > 0:
            difficulty = len(block.previous_hash) - len(block.previous_hash.lstrip('0'))
            total_difficulty += 2 ** difficulty
            total_time += time_diff
    
    if total_time > 0:
        return total_difficulty / total_time
    return 0.0
