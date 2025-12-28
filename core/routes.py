"""
Routes Flask pour l'application blockchain
Toutes les routes API et Web sont définies ici
"""
import time
from datetime import datetime
from flask import request, jsonify, render_template, redirect, url_for, send_file
from io import BytesIO
import os


def init_routes(app, bc, peers, node_id, node_port, base_reward, fee_per_tx, ai_queue, transaction_pool_ids):
    """
    Initialise toutes les routes Flask.
    
    Args:
        app: Instance Flask
        bc: Instance blockchain
        peers: Set des peers réseau
        node_id: ID du nœud
        node_port: Port du nœud
        base_reward: Récompense de base par bloc
        fee_per_tx: Frais par transaction
        ai_queue: Queue de transactions AI
        transaction_pool_ids: Set des IDs de transactions
    """
    from blockchain.transaction import Transaction
    from blockchain.block import Block
    from blockchain.fees_contract import mining_fee_contract
    from core.utils import find_transaction, get_latest_transactions, get_all_transactions, cleanup_transaction_pool
    
    # ============================================================
    # API RÉSEAU - Routes JSON
    # ============================================================
    
    @app.route('/chain', methods=['GET'])
    def full_chain():
        chain_data = bc.to_json_chain() 
        return jsonify({
            'chain': chain_data,
            'length': len(bc.chain)
        }), 200

    @app.route('/peers/register', methods=['POST'])
    def register_node():
        node_address = request.get_json().get('address')
        if not node_address:
            return "Erreur : Veuillez fournir une adresse de nœud valide.", 400
        
        peers.add(node_address)
        print(f"\n[OK] Nouveau pair enregistré via API: {node_address}")
        
        response = {
            'message': 'Nouveau pair ajouté',
            'total_peers': list(peers),
            'node_id': node_id
        }
        return jsonify(response), 201

    @app.route('/transactions/new', methods=['POST'])
    def new_transaction_api():
        """Route pour recevoir un lot de transactions d'un pair"""
        txs_data = request.get_json().get('transactions')
        
        if not txs_data:
            return "Erreur : transactions manquantes.", 400
        
        newly_added_txs = []
        duplicate_count = 0
        
        for tx_dict in txs_data:
            tx = Transaction(
                sender=tx_dict['sender'], 
                receiver=tx_dict['receiver'], 
                amount=tx_dict['amount'], 
                status=tx_dict.get('status', 'success'),
                signature=tx_dict.get('signature'), 
                timestamp_override=tx_dict['timestamp']
            )
            
            if tx.id not in transaction_pool_ids: 
                transaction_pool_ids.add(tx.id)
                newly_added_txs.append(tx)
            else:
                duplicate_count += 1
        
        if newly_added_txs:
            ai_queue.put(newly_added_txs)
            print(f"[NET] Reçu {len(newly_added_txs)} transactions. Ajoutées à la pool.")
            if duplicate_count > 0:
                 print(f"[WARN] {duplicate_count} transactions ignorées (déjà présentes).")

        return jsonify({"message": f"{len(newly_added_txs)} ajoutées. {duplicate_count} ignorées."}), 201

    @app.route('/nodes/resolve', methods=['GET'])
    def resolve_conflicts_api():
        """Route pour lancer le consensus"""
        replaced = bc.resolve_conflicts(peers)
        
        if replaced:
            response = {
                'message': 'Chaîne remplacée par la plus longue valide.',
                'new_chain': bc.to_json_chain()
            }
        else:
            response = {
                'message': 'La chaîne locale est canonique.',
                'chain': bc.to_json_chain()
            }
        return jsonify(response), 200

    @app.route('/blocks/receive', methods=['POST'])
    def receive_block():
        """Route pour recevoir un nouveau bloc d'un pair"""
        data = request.get_json()
        try:
            txs = [Transaction(t['sender'], t['receiver'], t.get('amount'), t.get('status', 'success'), 
                              t.get('signature'), t.get('timestamp')) for t in data.get('transactions', [])]
            new_block = Block(data['index'], txs, data['previous_hash'], data['proof'], 
                            data.get('timestamp'), data.get('hash'), data.get('miner'))

            last_block = bc.chain[-1]

            if new_block.index > last_block.index:
                print(f"\n[NET] Nouveau bloc détecté ({new_block.index}). Synchronisation...")
                replaced = bc.resolve_conflicts(peers)
                if replaced:
                    cleanup_transaction_pool(new_block.transactions, ai_queue, transaction_pool_ids, bc)
                    return jsonify({"message": "Chaîne mise à jour"}), 201

            elif new_block.index == last_block.index + 1:
                if bc.is_valid_chain([last_block, new_block]):
                    bc.add_block(new_block)
                    cleanup_transaction_pool(new_block.transactions, ai_queue, transaction_pool_ids, bc)
                    print(f"\n[OK] Bloc {new_block.index} ajouté.")
                    return jsonify({"message": "Bloc ajouté"}), 201

        except Exception as e:
            print(f"[ERR] Erreur réception bloc: {e}")
            return jsonify({"message": f"Erreur: {e}"}), 400

        return jsonify({"message": "Bloc rejeté ou déjà connu"}), 400

    # ============================================================
    # PAGES WEB - Vues HTML
    # ============================================================
    
    @app.route('/')
    def index():
        """Page d'accueil style Etherscan"""
        latest_txs = get_latest_transactions(bc, 5)
        
        unique_miners = set()
        for block in bc.chain:
            miner = getattr(block, 'miner', None)
            if miner:
                unique_miners.add(miner)
        
        total_supply = sum(bc.wallets.values())
        
        return render_template('home.html', 
                             chain=bc.chain, 
                             latest_txs=latest_txs,
                             total_supply=total_supply,
                             miner_balance=bc.get_balance(bc.miner_wallet),
                             miner_id=bc.miner_wallet,
                             nodes=list(unique_miners))

    @app.route('/search')
    def search():
        """Recherche universelle: bloc, TX ou adresse"""
        query = request.args.get('q', '').strip()
        
        if query.isdigit():
            idx = int(query)
            if idx < len(bc.chain):
                return redirect(url_for('view_block', index=idx))
        
        tx, _ = find_transaction(query, bc)
        if tx:
            return redirect(url_for('view_tx', tx_hash=query))
        
        return redirect(url_for('view_address', address=query))

    @app.route('/block/<int:index>')
    def view_block(index):
        """Page de détail d'un bloc"""
        if index >= len(bc.chain):
            return "Bloc introuvable", 404
        block = bc.chain[index]

        confirmations = len(bc.chain) - block.index - 1
        try:
            formatted_time = datetime.fromtimestamp(block.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            formatted_time = 'N/A'

        block_dict = block.to_dict()
        return render_template('block_detail.html', block=block, block_dict=block_dict, 
                             confirmations=confirmations, formatted_time=formatted_time)

    @app.route('/tx/<path:tx_hash>')
    def view_tx(tx_hash):
        """Page de détail d'une transaction"""
        tx, block_idx = find_transaction(tx_hash, bc)
        if not tx:
            return "Transaction introuvable", 404

        confirmations = len(bc.chain) - block_idx - 1 if block_idx is not None else 0

        try:
            formatted_time = datetime.fromtimestamp(tx.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            formatted_time = 'N/A'

        fee = fee_per_tx
        signature_valid = tx.is_signature_valid(tx.sender) if hasattr(tx, 'is_signature_valid') else False
        raw_json = tx.to_dict() if hasattr(tx, 'to_dict') else {}

        return render_template('transaction_detail.html', tx=tx, block_index=block_idx, 
                             confirmations=confirmations, formatted_time=formatted_time, 
                             fee=fee, signature_valid=signature_valid, raw_json=raw_json)

    @app.route('/address/<address>')
    def view_address(address):
        """Page de détail d'une adresse/portefeuille"""
        balance = bc.get_balance(address)
        successes, failures, internal = bc.get_history(address)

        total_received = 0.0
        total_sent = 0.0
        successes_list = successes or []
        for (_idx, tx) in successes_list:
            try:
                amt = float(getattr(tx, 'amount', 0) or 0)
            except Exception:
                amt = 0
            if getattr(tx, 'receiver', None) == address:
                total_received += amt
            if getattr(tx, 'sender', None) == address:
                total_sent += amt

        tx_count = len(successes_list) + (len(failures) if failures else 0)
        tab = request.args.get('tab', 'transactions')
        txs_all = list(reversed(successes_list))

        # Pagination
        if tab == 'transactions':
            try:
                page = int(request.args.get('page', 1))
            except Exception:
                page = 1
            try:
                per_page = int(request.args.get('per_page', 25))
            except Exception:
                per_page = 25
            total_txs = len(txs_all)
            total_pages = max(1, (total_txs + per_page - 1) // per_page)
            if page < 1:
                page = 1
            if page > total_pages:
                page = total_pages
            start = (page - 1) * per_page
            end = start + per_page
            paged_history = txs_all[start:end]
        else:
            page = 1
            per_page = 25
            total_txs = len(txs_all)
            total_pages = max(1, (total_txs + per_page - 1) // per_page)
            paged_history = txs_all[:per_page]

        txs = []
        for (b_idx, tx) in paged_history:
            try:
                time_str = datetime.fromtimestamp(tx.timestamp).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                time_str = 'N/A'
            txs.append({'block_index': b_idx, 'tx': tx, 'time': time_str})

        internal_list = list(reversed(internal or []))
        internal_formatted = []
        for it in internal_list:
            try:
                it_time = datetime.fromtimestamp(it.get('timestamp')).strftime('%Y-%m-%d %H:%M:%S') if it.get('timestamp') else 'N/A'
            except Exception:
                it_time = 'N/A'
            internal_formatted.append({
                'time': it_time, 
                'sender': it.get('sender'), 
                'receiver': it.get('receiver'), 
                'amount': it.get('amount'), 
                'label': it.get('label')
            })

        sent_count = 0
        if successes_list:
            sent_count += sum(1 for (_idx, tx) in successes_list if getattr(tx, 'sender', None) == address)
        if failures:
            sent_count += sum(1 for tx in failures if getattr(tx, 'sender', None) == address)
        fees_paid = sent_count * fee_per_tx

        miner_fees_received = 0.0
        for block in bc.chain:
            if getattr(block, 'miner', None) == address:
                miner_fees_received += len(getattr(block, 'transactions', [])) * fee_per_tx

        initial_balance = 5000.0
        is_miner = False
        for block in bc.chain:
            if getattr(block, 'miner', None) == address:
                initial_balance = 50000.0
                is_miner = True
                break
        
        total_received += miner_fees_received
        total_sent_with_fees = total_sent + fees_paid

        is_contract = False
        contract_data = None
        if hasattr(bc, 'contracts') and address in getattr(bc, 'contracts', {}):
            is_contract = True
            contract_data = getattr(bc, 'contracts', {}).get(address)

        return render_template('adresse.html', 
                             address=address, balance=balance, history=successes_list, 
                             txs=txs, failures=failures, internal=internal_formatted, 
                             page=page, per_page=per_page, total_txs=total_txs, total_pages=total_pages, 
                             total_received=total_received, total_sent=total_sent_with_fees, 
                             tx_count=tx_count, tab=tab, fees_paid=fees_paid, 
                             miner_fees_received=miner_fees_received, is_contract=is_contract, 
                             contract_data=contract_data, initial_balance=initial_balance)

    @app.route('/miners')
    def view_miners():
        """Page statistiques des mineurs"""
        try:
            miner_stats = {}
            total_blocks = len(bc.chain)
            now = time.time()
            
            for block in bc.chain:
                miner = getattr(block, 'miner', 'Unknown')
                if miner not in miner_stats:
                    miner_stats[miner] = {
                        'address': miner,
                        'blocks_mined': 0,
                        'total_rewards': 0,
                        'first_block': block.index,
                        'last_block': block.index,
                        'first_timestamp': getattr(block, 'timestamp', 0),
                        'last_timestamp': getattr(block, 'timestamp', 0)
                    }
                
                stats = miner_stats[miner]
                stats['blocks_mined'] += 1
                reward = base_reward + len(getattr(block, 'transactions', [])) * fee_per_tx
                stats['total_rewards'] += reward
                stats['last_block'] = block.index
                stats['last_timestamp'] = getattr(block, 'timestamp', 0)
            
            miners_list = []
            for miner, stats in miner_stats.items():
                percentage = (stats['blocks_mined'] / total_blocks * 100) if total_blocks > 0 else 0
                time_range = stats['last_timestamp'] - stats['first_timestamp']
                blocks_per_day = (stats['blocks_mined'] / (time_range / 86400)) if time_range > 86400 else stats['blocks_mined']
                
                time_since_last = int(now - stats['last_timestamp'])
                if time_since_last < 60:
                    last_seen = f"{time_since_last}s ago"
                elif time_since_last < 3600:
                    last_seen = f"{time_since_last // 60}m ago"
                elif time_since_last < 86400:
                    last_seen = f"{time_since_last // 3600}h ago"
                else:
                    last_seen = f"{time_since_last // 86400}d ago"
                
                miners_list.append({
                    'address': miner,
                    'blocks_mined': stats['blocks_mined'],
                    'percentage': round(percentage, 2),
                    'total_rewards': round(stats['total_rewards'], 2),
                    'avg_reward': round(stats['total_rewards'] / stats['blocks_mined'], 2),
                    'blocks_per_day': round(blocks_per_day, 2),
                    'first_block': stats['first_block'],
                    'last_block': stats['last_block'],
                    'last_seen': last_seen
                })
            
            miners_list.sort(key=lambda x: x['blocks_mined'], reverse=True)
            total_rewards_sum = sum(m['total_rewards'] for m in miners_list)
            
            return render_template('miners_simple.html', 
                                 miners=miners_list, 
                                 total_blocks=total_blocks,
                                 total_rewards=total_rewards_sum)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return render_template('error.html', message=str(e)), 500

    @app.route('/security')
    def view_security():
        """Page de sécurité IA: détection de fraude"""
        try:
            all_txs = []
            for block in bc.chain:
                for tx in getattr(block, 'transactions', []):
                    all_txs.append({
                        'tx': tx,
                        'block_index': block.index,
                        'timestamp': getattr(block, 'timestamp', 0)
                    })
            
            recent_txs = sorted(all_txs, key=lambda x: x['timestamp'], reverse=True)[:50]
            
            suspicious_patterns = []
            wallet_activity = {}
            
            for item in recent_txs:
                tx = item['tx']
                sender = tx.sender
                amount = tx.amount
                
                if sender not in wallet_activity:
                    wallet_activity[sender] = {'sent': 0, 'count': 0, 'amounts': [], 'transactions': []}
                wallet_activity[sender]['sent'] += amount
                wallet_activity[sender]['count'] += 1
                wallet_activity[sender]['amounts'].append(amount)
                wallet_activity[sender]['transactions'].append({'amount': amount, 'timestamp': item['timestamp']})
            
            for wallet, activity in wallet_activity.items():
                wallet_balance = bc.get_balance(wallet)
                
                if activity['count'] > 10:
                    suspicious_patterns.append({
                        'type': 'HIGH_FREQUENCY',
                        'wallet': wallet,
                        'description': f"Wallet avec {activity['count']} transactions (spam/bot possible)",
                        'severity': 'medium',
                        'tx_count': activity['count']
                    })
                
                if activity['sent'] > 1000:
                    suspicious_patterns.append({
                        'type': 'HIGH_VALUE',
                        'wallet': wallet,
                        'description': f"Volume élevé: {activity['sent']:.2f} EUR",
                        'severity': 'high',
                        'total_sent': activity['sent']
                    })
                
                amounts = activity['amounts']
                if len(amounts) > 3 and len(set(amounts)) == 1:
                    suspicious_patterns.append({
                        'type': 'WASH_TRADING',
                        'wallet': wallet,
                        'description': f"Montant identique répété {len(amounts)} fois: {amounts[0]} EUR",
                        'severity': 'high',
                        'repeated_amount': amounts[0]
                    })
                
                for tx_info in activity['transactions']:
                    tx_amount = tx_info['amount']
                    if wallet_balance > 0:
                        ratio = (tx_amount / wallet_balance) * 100
                        if ratio > 80:
                            suspicious_patterns.append({
                                'type': 'HIGH_BALANCE_RATIO',
                                'wallet': wallet,
                                'description': f"TX de {tx_amount:.2f} EUR = {ratio:.1f}% du solde",
                                'severity': 'high',
                                'ratio': ratio,
                                'tx_amount': tx_amount,
                                'balance': wallet_balance
                            })
                            break
            
            total_analyzed = len(recent_txs)
            suspicious_count = len(suspicious_patterns)
            trust_score = max(0, 100 - (suspicious_count * 5))
            
            suspicious_patterns.sort(key=lambda x: 0 if x['severity'] == 'high' else 1)
            
            return render_template('security.html',
                                 recent_txs=recent_txs[:20],
                                 suspicious_patterns=suspicious_patterns[:15],
                                 total_analyzed=total_analyzed,
                                 suspicious_count=suspicious_count,
                                 trust_score=trust_score)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return render_template('error.html', message=str(e)), 500

    @app.route('/blockchain-analysis')
    def blockchain_analysis():
        """Page d'analyse complète de la blockchain"""
        try:
            total_blocks = len(bc.chain)
            total_wallets = len(bc.wallets)
            total_txs = sum(len(block.transactions) for block in bc.chain)
            
            activity_counter = {}
            for block in bc.chain:
                for tx in block.transactions:
                    sender = getattr(tx, 'sender', None)
                    receiver = getattr(tx, 'receiver', None)
                    if sender:
                        activity_counter[sender] = activity_counter.get(sender, 0) + 1
                    if receiver:
                        activity_counter[receiver] = activity_counter.get(receiver, 0) + 1
            
            top_users = sorted(activity_counter.items(), key=lambda x: x[1], reverse=True)[:5]
            
            sorted_wallets = sorted(bc.wallets.items(), key=lambda x: x[1], reverse=True)[:10]
            total_wealth = sum(bc.wallets.values())
            top_3_wealth = sum(w[1] for w in sorted_wallets[:3])
            concentration_percentage = (top_3_wealth / total_wealth * 100) if total_wealth > 0 else 0
            
            miner_stats = {}
            for block in bc.chain:
                if block.index == 0:
                    continue
                miner = getattr(block, 'miner', None)
                if miner:
                    if miner not in miner_stats:
                        miner_stats[miner] = {'blocks': 0, 'rewards': 0}
                    miner_stats[miner]['blocks'] += 1
                    miner_stats[miner]['rewards'] += len(block.transactions) * fee_per_tx
            
            top_miners = sorted(miner_stats.items(), key=lambda x: x[1]['blocks'], reverse=True)[:3]
            
            recent_blocks = bc.chain[-10:] if len(bc.chain) > 10 else bc.chain
            recent_volume = sum(len(block.transactions) for block in recent_blocks)
            avg_txs_per_block = recent_volume / len(recent_blocks) if recent_blocks else 0
            
            return render_template('blockchain_analysis.html',
                                 total_blocks=total_blocks,
                                 total_wallets=total_wallets,
                                 total_txs=total_txs,
                                 top_users=top_users,
                                 sorted_wallets=sorted_wallets,
                                 concentration_percentage=concentration_percentage,
                                 top_miners=top_miners,
                                 avg_txs_per_block=avg_txs_per_block)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return render_template('error.html', message=str(e)), 500

    @app.route('/audit')
    def audit_page():
        """Page d'audit de portefeuille"""
        return render_template('audit.html')

    @app.route('/generate-audit/<address>')
    def generate_audit(address):
        """Génère un rapport d'audit PDF pour un portefeuille"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            import datetime as dt
            
            if address not in bc.wallets:
                return jsonify({'error': 'Portefeuille introuvable'}), 404
            
            balance = bc.get_balance(address)
            successes, failures, internal = bc.get_history(address)
            
            total_received = 0.0
            total_sent = 0.0
            successes_list = successes or []
            for (_idx, tx) in successes_list:
                amt = float(getattr(tx, 'amount', 0) or 0)
                if getattr(tx, 'receiver', None) == address:
                    total_received += amt
                if getattr(tx, 'sender', None) == address:
                    total_sent += amt
            
            sent_count = sum(1 for (_idx, tx) in successes_list if getattr(tx, 'sender', None) == address)
            fees_paid = sent_count * fee_per_tx
            
            miner_fees_received = 0.0
            blocks_mined = 0
            for block in bc.chain:
                if getattr(block, 'miner', None) == address:
                    blocks_mined += 1
                    miner_fees_received += len(getattr(block, 'transactions', [])) * fee_per_tx
            
            total_received += miner_fees_received
            initial_balance = 50000.0 if blocks_mined > 0 else 5000.0
            net_change = balance - initial_balance
            plus_value = max(0, net_change)
            moins_value = abs(min(0, net_change))
            
            timeline = []
            for (b_idx, tx) in successes_list[-10:]:
                try:
                    tx_time = dt.datetime.fromtimestamp(tx.timestamp).strftime('%d/%m/%Y %H:%M')
                    tx_type = "Reçu" if tx.receiver == address else "Envoyé"
                    timeline.append({
                        'date': tx_time,
                        'type': tx_type,
                        'amount': tx.amount,
                        'from': tx.sender[:20] + '...',
                        'to': tx.receiver[:20] + '...'
                    })
                except:
                    pass
            
            # Narrative Ollama
            narrative_context = f"""Expert comptable blockchain. Résumé narratif COURT (3-4 phrases) pour:
Adresse: {address}
Solde initial: {initial_balance:.2f}€
Actuel: {balance:.2f}€
Reçu: {total_received:.2f}€
Envoyé: {total_sent + fees_paid:.2f}€
Blocs minés: {blocks_mined}
TX: {len(successes_list)}
Factuel et professionnel."""
            
            try:
                import requests
                response = requests.post('http://localhost:11434/api/generate', 
                    json={'model': 'llama3.2', 'prompt': narrative_context, 'stream': False,
                          'options': {'temperature': 0.7, 'num_predict': 300}}, timeout=60)
                narrative = response.json().get('response', 'Analyse non disponible.') if response.status_code == 200 else 'Analyse non disponible.'
            except:
                narrative = 'Analyse IA non disponible (Ollama non démarré).'
            
            # PDF
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, 
                                  topMargin=2*cm, bottomMargin=2*cm)
            story = []
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, 
                                        textColor=colors.HexColor('#4F46E5'), alignment=TA_CENTER, spaceAfter=30)
            heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16, 
                                          textColor=colors.HexColor('#1F2937'), spaceAfter=12)
            normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, 
                                         textColor=colors.HexColor('#374151'))
            
            story.append(Paragraph("📊 RAPPORT D'AUDIT BLOCKCHAIN", title_style))
            story.append(Paragraph(f"Généré le {dt.datetime.now().strftime('%d/%m/%Y à %H:%M')}", styles['Normal']))
            story.append(Spacer(1, 0.5*cm))
            
            story.append(Paragraph("🔐 INFORMATIONS DU PORTEFEUILLE", heading_style))
            wallet_data = [
                ['Adresse:', address],
                ['Type:', 'Mineur' if blocks_mined > 0 else 'Utilisateur Standard'],
                ['Solde actuel:', f"{balance:.2f} €"],
                ['Statut:', 'Actif' if len(successes_list) > 0 else 'Inactif']
            ]
            wallet_table = Table(wallet_data, colWidths=[5*cm, 12*cm])
            wallet_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(wallet_table)
            story.append(Spacer(1, 0.5*cm))
            
            story.append(Paragraph("💰 RÉSUMÉ FINANCIER", heading_style))
            financial_data = [
                ['Capital initial', f"{initial_balance:.2f} €"],
                ['Total reçu (avec frais minage)', f"{total_received:.2f} €"],
                ['Total envoyé', f"{total_sent:.2f} €"],
                ['Frais de transaction payés', f"{fees_paid:.2f} €"],
                ['Solde final', f"{balance:.2f} €"],
                ['', ''],
                ['Plus-value', f"+{plus_value:.2f} €" if plus_value > 0 else '0.00 €'],
                ['Moins-value', f"-{moins_value:.2f} €" if moins_value > 0 else '0.00 €'],
            ]
            financial_table = Table(financial_data, colWidths=[10*cm, 7*cm])
            financial_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 4), colors.white),
                ('BACKGROUND', (0, 6), (-1, -1), colors.HexColor('#FEF3C7')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 4), (1, 4), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ]))
            story.append(financial_table)
            story.append(Spacer(1, 0.5*cm))
            
            story.append(Paragraph("🤖 ANALYSE NARRATIVE (IA)", heading_style))
            story.append(Paragraph(narrative, normal_style))
            story.append(Spacer(1, 1*cm))
            
            if timeline:
                story.append(Paragraph("📅 TIMELINE DES 10 DERNIÈRES TRANSACTIONS", heading_style))
                timeline_data = [['Date', 'Type', 'Montant', 'De', 'Vers']]
                for t in timeline:
                    timeline_data.append([t['date'], t['type'], f"{t['amount']:.2f} €", t['from'], t['to']])
                timeline_table = Table(timeline_data, colWidths=[3*cm, 2*cm, 2.5*cm, 4.5*cm, 4.5*cm])
                timeline_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
                ]))
                story.append(timeline_table)
            
            story.append(Spacer(1, 1*cm))
            story.append(Paragraph("━" * 100, styles['Normal']))
            story.append(Paragraph("Document généré automatiquement par BlockchainIA.", styles['Italic']))
            story.append(Paragraph("⚠️ Rapport informatif. Consultez un expert fiscal pour déclarations officielles.", styles['Italic']))
            
            doc.build(story)
            buffer.seek(0)
            
            return send_file(buffer, mimetype='application/pdf', as_attachment=True, 
                           download_name=f'audit_{address[:10]}.pdf')
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/wallet-preview/<address>')
    def wallet_preview(address):
        """API pour aperçu rapide d'un portefeuille"""
        try:
            if address not in bc.wallets:
                return jsonify({'error': 'Portefeuille introuvable'}), 404
            
            balance = bc.get_balance(address)
            successes, failures, internal = bc.get_history(address)
            
            total_received = 0.0
            total_sent = 0.0
            successes_list = successes or []
            for (_idx, tx) in successes_list:
                amt = float(getattr(tx, 'amount', 0) or 0)
                if getattr(tx, 'receiver', None) == address:
                    total_received += amt
                if getattr(tx, 'sender', None) == address:
                    total_sent += amt
            
            sent_count = sum(1 for (_idx, tx) in successes_list if getattr(tx, 'sender', None) == address)
            fees_paid = sent_count * fee_per_tx
            
            blocks_mined = 0
            miner_fees_received = 0.0
            for block in bc.chain:
                if getattr(block, 'miner', None) == address:
                    blocks_mined += 1
                    miner_fees_received += len(getattr(block, 'transactions', [])) * fee_per_tx
            
            total_received += miner_fees_received
            initial_balance = 50000.0 if blocks_mined > 0 else 5000.0
            net_change = balance - initial_balance
            
            narrative_context = f"""Expert comptable blockchain. Résumé COURT (3-4 phrases):
Adresse: {address}
Initial: {initial_balance:.2f}€, Actuel: {balance:.2f}€
Reçu: {total_received:.2f}€, Envoyé: {total_sent + fees_paid:.2f}€
Blocs minés: {blocks_mined}, TX: {len(successes_list)}
Factuel et professionnel."""
            
            try:
                import requests
                response = requests.post('http://localhost:11434/api/generate', 
                    json={'model': 'llama3.2', 'prompt': narrative_context, 'stream': False,
                          'options': {'temperature': 0.7, 'num_predict': 300}}, timeout=60)
                narrative = response.json().get('response', 'Analyse non disponible.') if response.status_code == 200 else 'Analyse non disponible.'
            except:
                narrative = 'Analyse IA non disponible (Ollama non démarré).'
            
            return jsonify({
                'balance': f"{balance:.2f}",
                'tx_count': len(successes_list),
                'total_received': f"{total_received:.2f}",
                'total_sent': f"{total_sent + fees_paid:.2f}",
                'fees_paid': f"{fees_paid:.2f}",
                'blocks_mined': blocks_mined,
                'net_change': f"{net_change:.2f}",
                'narrative': narrative
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/blocks')
    def view_blocks():
        """Liste tous les blocs avec pagination"""
        try:
            try:
                page = int(request.args.get('page', 1))
            except Exception:
                page = 1
            if page < 1:
                page = 1

            try:
                per_page = int(request.args.get('per_page', 25))
            except Exception:
                per_page = 25
            if per_page <= 0:
                per_page = 25

            all_blocks = []
            now = time.time()
            for block in reversed(bc.chain):
                age_seconds = int(now - getattr(block, 'timestamp', now))
                if age_seconds < 60:
                    age = f"{age_seconds}s"
                elif age_seconds < 3600:
                    age = f"{age_seconds // 60}m"
                elif age_seconds < 86400:
                    age = f"{age_seconds // 3600}h"
                else:
                    age = f"{age_seconds // 86400}d"

                reward = base_reward + len(getattr(block, 'transactions', [])) * fee_per_tx
                all_blocks.append({
                    'index': block.index,
                    'hash': getattr(block, 'hash', 'N/A'),
                    'hash_short': (getattr(block, 'hash', '')[:16] + '...') if getattr(block, 'hash', None) else 'N/A',
                    'miner': getattr(block, 'miner', 'Unknown'),
                    'tx_count': len(getattr(block, 'transactions', [])),
                    'age': age,
                    'timestamp': getattr(block, 'timestamp', 0),
                    'reward': reward
                })

            total = len(all_blocks)
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1

            if page > total_pages:
                page = total_pages

            start = (page - 1) * per_page
            end = start + per_page
            paged_blocks = all_blocks[start:end]

            return render_template('blocks_list.html', blocks=paged_blocks, total=total, 
                                 page=page, per_page=per_page, total_pages=total_pages)
        except Exception as e:
            print(f"[ERR] Erreur view_blocks: {e}")
            return render_template('error.html', error=str(e)), 500

    @app.route('/transactions')
    def view_transactions():
        """Liste toutes les transactions avec pagination"""
        try:
            page = int(request.args.get('page', 1))
        except Exception:
            page = 1
        if page < 1:
            page = 1
        try:
            per_page = int(request.args.get('per_page', 25))
        except Exception:
            per_page = 25
        if per_page <= 0:
            per_page = 25

        all_txs = get_all_transactions(bc)
        now = time.time()
        enriched = []
        for item in all_txs:
            tx = item['tx']
            txid = getattr(tx, 'id', None) or getattr(tx, 'hash', None)
            if not txid:
                txid = f"0x{hash(str(tx))}"
            age_seconds = int(now - getattr(tx, 'timestamp', now))
            if age_seconds < 60:
                age = f"{age_seconds}s"
            elif age_seconds < 3600:
                age = f"{age_seconds // 60}m"
            elif age_seconds < 86400:
                age = f"{age_seconds // 3600}h"
            else:
                age = f"{age_seconds // 86400}d"

            enriched.append({
                'tx': tx,
                'txid': txid,
                'from': getattr(tx, 'sender', ''),
                'to': getattr(tx, 'receiver', ''),
                'amount': getattr(tx, 'amount', 0),
                'block_index': item.get('block_index'),
                'time': item.get('time'),
                'age': age
            })

        total = len(enriched)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        if page > total_pages:
            page = total_pages
        start = (page - 1) * per_page
        end = start + per_page
        paged = enriched[start:end]

        return render_template('transactions_list.html', transactions=paged, total=total, 
                             page=page, per_page=per_page, total_pages=total_pages)

    # Gestionnaire d'erreur 500
    @app.errorhandler(500)
    def internal_server_error(e):
        try:
            print(f"[ERR] Internal server error: {e}")
        except Exception:
            pass
        return render_template('error.html', error=str(e)), 500

    # ============================================================
    # EXPORTS CSV/JSON
    # ============================================================
    
    @app.route('/export/blocks.csv')
    def export_blocks_csv():
        from io import StringIO
        from core import db as _db
        _db.sync_from_blockchain(bc)
        si = StringIO()
        _db.export_blocks_csv(si)
        si.seek(0)
        return app.response_class(si.getvalue(), mimetype='text/csv', 
                                headers={"Content-Disposition": "attachment; filename=blocks.csv"})

    @app.route('/export/transactions.csv')
    def export_transactions_csv():
        from io import StringIO
        from core import db as _db
        _db.sync_from_blockchain(bc)
        si = StringIO()
        _db.export_transactions_csv(si)
        si.seek(0)
        return app.response_class(si.getvalue(), mimetype='text/csv', 
                                headers={"Content-Disposition": "attachment; filename=transactions.csv"})

    @app.route('/export/transactions/<address>.csv')
    def export_transactions_for_address_csv(address):
        from io import StringIO
        from core import db as _db
        _db.sync_from_blockchain(bc)
        si = StringIO()
        _db.export_transactions_csv_for_address(si, address)
        si.seek(0)
        filename = f"transactions_{address}.csv"
        return app.response_class(si.getvalue(), mimetype='text/csv', 
                                headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.route('/download')
    def download_page():
        """Page de téléchargement du projet"""
        return render_template('download.html', network_id='NETWORK_ID', node_port=node_port)

    @app.route('/download/project.zip')
    def download_project():
        """Télécharge le projet en ZIP"""
        import zipfile
        
        memory_file = BytesIO()
        
        exclude_patterns = {
            '__pycache__', 'venv', '.git', '.vscode', 
            'blockchain_data.json', 'blockchain.db', 'peers.json',
            '*.pyc', '.DS_Store'
        }
        
        def should_exclude(path):
            for pattern in exclude_patterns:
                if pattern in path or path.endswith(pattern.replace('*', '')):
                    return True
            return False
        
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Remonter d'un niveau pour obtenir la racine du projet (depuis core/)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            for root, dirs, files in os.walk(project_root):
                dirs[:] = [d for d in dirs if not should_exclude(d)]
                
                for file in files:
                    if should_exclude(file):
                        continue
                        
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, project_root)
                    
                    try:
                        zf.write(file_path, arcname)
                    except Exception as e:
                        print(f"[WARN] Impossible d'ajouter {file}: {e}")
        
        memory_file.seek(0)
        return send_file(memory_file, mimetype='application/zip', as_attachment=True, 
                       download_name='blockchain_project.zip')

    @app.route('/api/chain_data')
    def chain_data():
        """API pour visualiseur 3D"""
        chain_list = []
        for block in bc.chain:
            tx_list_dicts = [tx.to_dict() if hasattr(tx, 'to_dict') else tx for tx in block.transactions]
            block_dict = {
                'index': block.index, 'timestamp': block.timestamp,
                'transactions': tx_list_dicts, 'hash': block.hash,
                'previous_hash': block.previous_hash, 
                'miner': block.miner if hasattr(block, 'miner') else "Unknown"
            }
            chain_list.append(block_dict)
        return jsonify(chain_list)

    @app.route('/ask', methods=['POST'])
    def ask_ai():
        """Route pour poser des questions à l'assistant IA via Ollama"""
        try:
            data = request.get_json()
            question = data.get('question', '').strip()
            
            if not question:
                return jsonify({'error': 'Question vide'}), 400
            
            context = f"""Assistant technique spécialisé en analyse de blockchain.
Réponds uniquement sur blockchain, cryptomonnaies, sécurité des réseaux.

Informations:
- Blocs: {len(bc.chain)}
- Frais/TX: {fee_per_tx}€
- Reward/bloc: {base_reward}€

Question: {question}

Factuel et technique en MAXIMUM 3-4 phrases courtes en français."""
            
            import requests
            response = requests.post('http://localhost:11434/api/generate', 
                json={'model': 'llama3.2', 'prompt': context, 'stream': False,
                      'options': {'temperature': 0.7, 'num_predict': 600}}, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', 'Désolé, pas de réponse.')
                return jsonify({'answer': answer})
            else:
                return jsonify({'error': 'Ollama non disponible'}), 503
                
        except Exception as e:
            return jsonify({'error': f'Erreur: {str(e)}'}), 500

    @app.route('/analyze-blockchain', methods=['POST'])
    def analyze_blockchain():
        """Route pour analyser la blockchain avec données complètes"""
        try:
            data = request.get_json()
            question = data.get('question', '').strip()
            
            if not question:
                return jsonify({'error': 'Question vide'}), 400
            
            total_blocks = len(bc.chain)
            total_wallets = len(bc.wallets)
            total_txs = sum(len(block.transactions) for block in bc.chain)
            
            activity_counter = {}
            for block in bc.chain:
                for tx in block.transactions:
                    sender = getattr(tx, 'sender', None)
                    receiver = getattr(tx, 'receiver', None)
                    if sender:
                        activity_counter[sender] = activity_counter.get(sender, 0) + 1
                    if receiver:
                        activity_counter[receiver] = activity_counter.get(receiver, 0) + 1
            top_users = sorted(activity_counter.items(), key=lambda x: x[1], reverse=True)[:5]
            
            sorted_wallets = sorted(bc.wallets.items(), key=lambda x: x[1], reverse=True)
            richest_wallets = sorted_wallets[:5]
            poorest_wallets = sorted_wallets[-5:] if len(sorted_wallets) > 5 else sorted_wallets
            
            total_wealth = sum(bc.wallets.values())
            top_3_wealth = sum(w[1] for w in sorted_wallets[:3]) if len(sorted_wallets) >= 3 else total_wealth
            concentration_percentage = (top_3_wealth / total_wealth * 100) if total_wealth > 0 else 0
            
            miner_stats = {}
            for block in bc.chain:
                if block.index == 0:
                    continue
                miner = getattr(block, 'miner', None)
                if miner:
                    if miner not in miner_stats:
                        miner_stats[miner] = {'blocks': 0, 'rewards': 0}
                    miner_stats[miner]['blocks'] += 1
                    miner_stats[miner]['rewards'] += len(block.transactions) * fee_per_tx
            top_miners = sorted(miner_stats.items(), key=lambda x: x[1]['blocks'], reverse=True)[:5]
            
            context = f"""Analyste blockchain expert répondant UNIQUEMENT sur NOTRE blockchain.

DONNÉES RÉELLES:
- Blocs: {total_blocks}, Portefeuilles: {total_wallets}, TX: {total_txs}
- Richesse totale: {total_wealth:.2f}€
- Concentration: {concentration_percentage:.1f}% (top 3)

Top 5 actifs:
"""
            for i, (user, count) in enumerate(top_users, 1):
                context += f"{i}. {user} - {count} interactions\n"
            
            context += f"\nTop 5 PLUS RICHES:\n"
            for i, (wallet, balance) in enumerate(richest_wallets, 1):
                context += f"{i}. {wallet}: {balance:.2f}€\n"
            
            context += f"\nTop 5 MOINS RICHES:\n"
            for i, (wallet, balance) in enumerate(poorest_wallets, 1):
                context += f"{i}. {wallet}: {balance:.2f}€\n"
            
            context += f"\nTop 5 mineurs:\n"
            for i, (miner, stats) in enumerate(top_miners, 1):
                context += f"{i}. {miner}: {stats['blocks']} blocs, {stats['rewards']:.2f}€\n"
            
            context += f"""
Question: {question}

INSTRUCTIONS:
- 3-5 phrases max, concis et professionnel
- Base-toi UNIQUEMENT sur les données ci-dessus
- MOINS d'argent → section "MOINS RICHES"
- PLUS d'argent → section "PLUS RICHES"
- Cite adresses et montants exacts
"""
            
            import requests
            response = requests.post('http://localhost:11434/api/generate', 
                json={'model': 'llama3.2', 'prompt': context, 'stream': False,
                      'options': {'temperature': 0.7, 'num_predict': 800}}, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', 'Désolé, pas de réponse.')
                return jsonify({'answer': answer})
            else:
                return jsonify({'error': 'Ollama non disponible'}), 503
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Erreur: {str(e)}'}), 500
