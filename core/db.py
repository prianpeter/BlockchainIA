"""Module de persistance SQLite via SQLAlchemy.

Fournit:
- modèles : Block, Transaction, Wallet, InternalTx, Stake
- fonctions d'init / sync / save / export
"""
from sqlalchemy import (create_engine, Column, Integer, String, Float, Text, ForeignKey)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, relationship
from sqlalchemy.exc import IntegrityError
import os
import json

Base = declarative_base()

class BlockModel(Base):
    __tablename__ = 'blocks'
    index = Column(Integer, primary_key=True)
    hash = Column(String, index=True)
    previous_hash = Column(String)
    timestamp = Column(Float)
    miner = Column(String, index=True)
    tx_count = Column(Integer)
    nonce = Column(Integer)
    reward = Column(Float)

class TransactionModel(Base):
    __tablename__ = 'transactions'
    id = Column(String, primary_key=True)
    sender = Column(String, index=True)
    receiver = Column(String, index=True)
    amount = Column(Float)
    status = Column(String)
    signature = Column(Text)
    timestamp = Column(Float)
    block_index = Column(Integer, ForeignKey('blocks.index'))

class WalletModel(Base):
    __tablename__ = 'wallets'
    id = Column(String, primary_key=True)
    balance = Column(Float)

class InternalTxModel(Base):
    __tablename__ = 'internal_tx'
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender = Column(String)
    receiver = Column(String)
    amount = Column(Float)
    timestamp = Column(Float)
    label = Column(String)

_engine = None
_Session = None


def init_db(db_path=None):
    global _engine, _Session
    if db_path is None:
        db_path = os.getenv('BLOCKCHAIN_DB_URL', 'sqlite:///blockchain.db')

    _engine = create_engine(db_path, connect_args={"check_same_thread": False})
    _Session = scoped_session(sessionmaker(bind=_engine))
    Base.metadata.create_all(_engine)


def get_session():
    if _Session is None:
        raise RuntimeError("Database not initialised - call init_db first")
    return _Session()


def save_block(block, reward=None):
    """Sauve un bloc et ses transactions dans la DB."""
    sess = get_session()
    try:
        bm = sess.get(BlockModel, block.index)
        if not bm:
            bm = BlockModel(index=block.index, hash=getattr(block, 'hash', None), previous_hash=getattr(block, 'previous_hash', None),
                            timestamp=getattr(block, 'timestamp', None), miner=getattr(block, 'miner', None), tx_count=len(getattr(block, 'transactions', [])), nonce=getattr(block, 'nonce', 0), reward=reward)
            sess.add(bm)
        else:
            bm.hash = block.hash
            bm.previous_hash = block.previous_hash
            bm.timestamp = block.timestamp
            bm.miner = getattr(block, 'miner', None)
            bm.tx_count = len(block.transactions)
            bm.nonce = getattr(block, 'nonce', 0)
            bm.reward = reward

        # Transactions
        import hashlib
        for tx in getattr(block, 'transactions', []):
            txid = getattr(tx, 'id', None) or getattr(tx, 'hash', None)
            if not txid:
                # Fallback deterministic ID
                raw = f"{getattr(tx, 'sender', '')}{getattr(tx, 'receiver', '')}{getattr(tx, 'amount', '')}{getattr(tx, 'timestamp', '')}"
                txid = '0x' + hashlib.sha256(raw.encode()).hexdigest()
            tm = sess.get(TransactionModel, txid)
            if not tm:
                tm = TransactionModel(id=txid, sender=getattr(tx, 'sender', None), receiver=getattr(tx, 'receiver', None),
                                      amount=getattr(tx, 'amount', 0), status=getattr(tx, 'status', None), signature=getattr(tx, 'signature', None),
                                      timestamp=getattr(tx, 'timestamp', None), block_index=block.index)
                sess.add(tm)
            else:
                tm.block_index = block.index
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def upsert_wallets(wallets):
    sess = get_session()
    try:
        for wid, bal in wallets.items():
            w = sess.get(WalletModel, wid)
            if not w:
                w = WalletModel(id=wid, balance=bal)
                sess.add(w)
            else:
                w.balance = bal
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def save_internal_txs(internal_list):
    sess = get_session()
    try:
        for it in internal_list:
            itm = InternalTxModel(sender=it.get('sender'), receiver=it.get('receiver'), amount=it.get('amount'), timestamp=it.get('timestamp'), label=it.get('label'))
            sess.add(itm)
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def export_blocks_csv(path_or_fileobj):
    sess = get_session()
    try:
        rows = sess.query(BlockModel).order_by(BlockModel.index.desc()).all()
        header = 'index,hash,previous_hash,timestamp,miner,tx_count,nonce,reward\n'
        path_or_fileobj.write(header)
        for r in rows:
            line = f"{r.index},{r.hash},{r.previous_hash},{r.timestamp},{r.miner},{r.tx_count},{r.nonce},{r.reward}\n"
            path_or_fileobj.write(line)
    finally:
        sess.close()


def export_transactions_csv(path_or_fileobj):
    sess = get_session()
    try:
        rows = sess.query(TransactionModel).order_by(TransactionModel.timestamp.desc()).all()
        header = 'id,sender,receiver,amount,status,timestamp,block_index\n'
        path_or_fileobj.write(header)
        for r in rows:
            line = f"{r.id},{r.sender},{r.receiver},{r.amount},{r.status},{r.timestamp},{r.block_index}\n"
            path_or_fileobj.write(line)
    finally:
        sess.close()


def export_transactions_csv_for_address(path_or_fileobj, address):
    sess = get_session()
    try:
        rows = sess.query(TransactionModel).filter((TransactionModel.sender == address) | (TransactionModel.receiver == address)).order_by(TransactionModel.timestamp.desc()).all()
        header = 'id,sender,receiver,amount,status,timestamp,block_index\n'
        path_or_fileobj.write(header)
        for r in rows:
            line = f"{r.id},{r.sender},{r.receiver},{r.amount},{r.status},{r.timestamp},{r.block_index}\n"
            path_or_fileobj.write(line)
    finally:
        sess.close()


def export_chain_json(path_or_fileobj):
    sess = get_session()
    try:
        blocks = sess.query(BlockModel).order_by(BlockModel.index.asc()).all()
        out = []
        for b in blocks:
            txs = sess.query(TransactionModel).filter(TransactionModel.block_index == b.index).all()
            tlist = []
            for t in txs:
                tlist.append({
                    'id': t.id, 'sender': t.sender, 'receiver': t.receiver, 'amount': t.amount, 'status': t.status, 'timestamp': t.timestamp
                })
            out.append({'index': b.index, 'hash': b.hash, 'previous_hash': b.previous_hash, 'timestamp': b.timestamp, 'miner': b.miner, 'transactions': tlist, 'reward': b.reward})
        path_or_fileobj.write(json.dumps(out, indent=2))
    finally:
        sess.close()


def sync_from_blockchain(bc):
    """Synchronise l'état actuel de la blockchain en DB (import initial)."""
    # Simple : on supprime tout et on réimporte (idempotent pour dev)
    sess = get_session()
    try:
        # Nota: pour simplifier, on drop all rows
        from sqlalchemy import text
        sess.execute(text('DELETE FROM transactions'))
        sess.execute(text('DELETE FROM blocks'))
        sess.execute(text('DELETE FROM wallets'))
        sess.execute(text('DELETE FROM internal_tx'))
        sess.commit()

        # Réimporter en parcourant la chaîne
        for block in bc.chain:
            # Estimer reward comme base + tx_count * fee si disponible
            tx_count = len(getattr(block, 'transactions', []))
            est_reward = 5.0 + tx_count * 1.0
            save_block(block, reward=est_reward)
        # Wallets
        upsert_wallets(bc.wallets)
        # Internal txs
        save_internal_txs(bc.internal_tx_history)
    finally:
        sess.close()
