import random
import time # NÉCESSAIRE
from ollama import chat
from blockchain.transaction import Transaction
from blockchain.fees_contract import mining_fee_contract


def parse_ollama_lines_to_pairs(text):
    pairs = []
    # ... (logique inchangée)
    for line in text.splitlines():
        if "->" in line and ":" in line:
            try:
                left, right = line.split("->", 1)
                sender = left.strip()
                recep, amt_part = right.split(":", 1)
                receiver = recep.strip()
                # ne garder que les chiffres pour le montant
                amt_str = ''.join(ch for ch in amt_part if ch.isdigit())
                if not amt_str:
                    continue
                amt = int(amt_str)
                # vérifier format simple des adresses
                if sender.startswith("0x") and receiver.startswith("0x"):
                    pairs.append((sender, receiver, amt))
            except Exception:
                continue
    return pairs

def generate_ai_transactions(blockchain, n=4):
    # Appel à Ollama
    pairs = []
    current_time = time.time() # Temps de référence
    
    try:
        # PROMPT MIS À JOUR : Montants augmentés (100 à 3000) pour réintroduire le risque
        prompt = (
            f"Génère exactement {n} transactions fictives au format EXACT par ligne :\n"
            "0x{emetteur} -> 0x{receveur} : {montant}\n"
            "- Adresses : 0x + 16 caractères hex\n"
            "- Montants entiers entre 100 et 3000\n" 
            "- Répond uniquement par les lignes de transactions, sans explications ni préambule.\n"
            "- Utilise des montants variés pour simuler des transactions réelles."
        )
        resp = chat(model="llama3.2", messages=[{"role":"user","content":prompt}])
        text = resp['message']['content']
        pairs = parse_ollama_lines_to_pairs(text)
    except Exception:
        pairs = []

    transactions = []
    
    for sender, receiver, amount in pairs[:n]: 
        if sender not in blockchain.wallets:
            blockchain.wallets[sender] = random.randint(5000, 20000) 
        if receiver not in blockchain.wallets:
            blockchain.wallets[receiver] = random.randint(5000, 20000)
        
        # NOUVEAU : Calcul du timestamp aléatoire (dans la minute précédant)
        random_offset = random.uniform(0, 60) # Offset de 0 à 60 secondes
        tx_time = current_time - random_offset
        
        # Le create_transaction vérifie si l'émetteur a les fonds et utilise le timestamp
        tx = blockchain.create_transaction(sender, receiver, amount, timestamp_override=tx_time)
        
        if tx:
            transactions.append(tx)
        
        if len(transactions) >= n:
            break

    return transactions