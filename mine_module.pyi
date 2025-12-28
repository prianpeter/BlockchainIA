"""Type stubs for mine_module C++ extension."""

def mine_pow(base: str, difficulty: int) -> tuple[int, str]:
    """
    Mine a block using Proof-of-Work algorithm (C++ implementation).
    
    Args:
        base: JSON string of block data (without nonce)
        difficulty: Number of leading zeros required in hash
    
    Returns:
        Tuple of (nonce, hash) where:
        - nonce: The found nonce value (int)
        - hash: The resulting hash (str)
    """
    ...
