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
