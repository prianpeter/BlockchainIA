# blockchainIA

Ce projet est une application de blockchain/minage écrite en Python, avec des modules natifs C++ pour l'accélération du minage.

## Prérequis

- Python 3.11 ou supérieur
- pip (gestionnaire de paquets Python)
- Un compilateur C++ (pour le module natif, si recompilation nécessaire)


## Installation

1. **Cloner le dépôt**

```bash
git clone https://github.com/prianos/BlockchainIA.git
cd BlockchainIA
```

2. **Créer et activer un environnement virtuel Python**

Sous Windows :
```bash
python -m venv venv
venv\Scripts\activate
```
Sous Linux/Mac :
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Installer les dépendances Python dans le venv**

```bash
pip install -r requirements.txt
```

4. **Compiler le module natif C++ dans le venv (si nécessaire)**

Si le module `mine_module` n'est pas déjà compilé pour votre plateforme :

```bash
python setup.py build_ext --inplace
```

Assurez-vous que l'environnement virtuel est bien activé lors de la compilation et de l'utilisation du projet.


## Utilisation

Lancer l'application principale :

```bash
python main.py
```

L'application lance un serveur web (par défaut sur http://127.0.0.1:5000). Ouvrez ce lien dans votre navigateur pour accéder à l'interface.

### Exemples de choses à faire

- **Créer un bloc** :
	- Depuis l'interface web, allez sur la page "Ajouter une transaction" ou "Miner un bloc" selon les options disponibles.
	- Remplissez les champs requis et validez pour générer une transaction ou miner un nouveau bloc.

- **Consulter la blockchain** :
	- Naviguez dans les menus pour voir la liste des blocs, le détail d'un bloc ou d'une transaction.

- **Utiliser l'IA avec Ollama** :
	- Assurez-vous qu'Ollama est lancé localement (par défaut sur http://localhost:11434).
	- Depuis l'interface, accédez à la section IA (par exemple "Audit IA" ou "Générateur IA").
	- Entrez une requête, par exemple :
		- "Analyse la sécurité de la blockchain."
		- "Génère un résumé des transactions du dernier bloc."
	- L'IA répondra directement dans l'interface.

- **Exemple de requête API (avancé)** :
	- Vous pouvez interagir avec l'API REST (si activée) via curl ou Postman, par exemple :
		```bash
		curl http://127.0.0.1:5000/api/blocks
		```

N'hésitez pas à explorer l'interface web pour découvrir toutes les fonctionnalités disponibles.

## Utilisation avancée : minage à plusieurs (option 5 et 6)

> **Facultatif :**
> 
> Pour utiliser l'**option 5** (connexion à un autre ordinateur pour miner à deux), il est nécessaire que les deux ordinateurs soient sur le **même réseau local** (Wi-Fi/ethernet) ou connectés via un service comme **Zerotier** (VPN privé).
>
> **Étapes recommandées :**
> 1. Sur chaque ordinateur, lancez l'application normalement.
>    - Il est conseillé de configurer chaque application sur un **port différent** (par exemple 5000 et 5001) pour éviter les conflits.
> 2. Utilisez l'**option 6** pour ajouter l'adresse de l'autre ordinateur et synchroniser la blockchain. Cela permet d'avoir la même blockchain sur les deux machines.
>    - Avant la synchronisation, il est recommandé de **miner quelques blocs sur l'une des deux blockchains** afin d'obtenir une chaîne plus longue (la plus longue sera conservée lors de la synchronisation).
> 3. Vous pouvez alors miner à deux sur la même blockchain, les blocs seront partagés et synchronisés entre les deux ordinateurs.
>
> ⚠️ Assurez-vous que les ports nécessaires sont ouverts sur les deux machines et que les pare-feux ne bloquent pas la connexion.

## Structure du projet

- `main.py` : point d'entrée principal
- `ai/` : modules d'IA
- `blockchain/` : logique blockchain, transactions, blocs
- `core/` : utilitaires, base de données, fonctions de minage
- `templates/` : templates HTML pour l'interface web
- `mine_module.pyi`, `mine_pow.cpp` : module natif pour le minage
- `requirements.txt` : dépendances Python
- `setup.py` : script de compilation du module natif


## Notes

- Il est nécessaire d'activer Ollama (serveur local de modèles IA) pour que toutes les fonctionnalités d'IA du projet fonctionnent correctement. Consultez la documentation d'Ollama pour l'installation et le démarrage.

- Pour toute question ou contribution, ouvrez une issue ou une pull request.
***
