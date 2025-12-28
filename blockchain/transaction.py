# blockchain/transaction.py
import time
import hashlib
import json

class Transaction:
    def __init__(self, sender, receiver, amount, status="success", signature=None, timestamp_override=None):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.status = status
        self.signature = signature
        self.timestamp = timestamp_override if timestamp_override else time.time()
        
        # On utilise "id" pour être cohérent avec le reste de ton code
        self.id = self.calculate_id()

    def calculate_id(self):
        data_string = json.dumps({
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp
        }, sort_keys=True)
        # On ajoute 0x au début du hash
        hash_hash = hashlib.sha256(data_string.encode()).hexdigest()
        return f"0x{hash_hash}"

    def to_dict(self):
        return {
            'id': self.id,  # <--- Vérifie bien que c'est 'id' et pas 'hash'
            'sender': self.sender,
            'receiver': self.receiver,
            'amount': self.amount,
            'status': self.status,
            'timestamp': self.timestamp,
            'signature': self.signature
        }
    # --- LOGIQUE DE SIGNATURE ---

    def sign(self, private_key):
        """Simule la signature de la transaction en utilisant l'ID de la TX."""
        data_to_sign = str(self.id) + str(private_key) 
        self.signature = hashlib.sha256(data_to_sign.encode()).hexdigest()

    def is_signature_valid(self, public_key):
        """Vérifie si la signature correspond à l'émetteur."""
        if not self.signature:
            return False 
        data_to_verify = str(self.id) + str(public_key)
        expected_signature = hashlib.sha256(data_to_verify.encode()).hexdigest()
        return self.signature == expected_signature

    def __str__(self):
        """Utilisé pour l'affichage des transactions échouées dans le menu."""
        sign_status = "[OK]" if self.signature else "[ERR]"
        # Ici on affiche les IDs complets comme tu l'as demandé
        return f"[{self.status.upper()}] {self.sender} -> {self.receiver} | {self.amount} € (Sign: {sign_status})"
    
    def compact(self):
        """Version compacte pour le hachage de bloc."""
        return f"{self.sender[:6]}:{self.receiver[:6]}:{self.amount}"