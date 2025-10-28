import os
import json
import re
import traceback
import ast
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")

# Vérifie l'existence du dossier data
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- Utilitaires ---
def load_admin_ips():
    if not os.path.exists(ADMIN_FILE):
        return []
    with open(ADMIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_projects():
    if not os.path.exists(PROJECT_FILE):
        return {}
    with open(PROJECT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_projects(projects):
    with open(PROJECT_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=4)


# --- Routes principales ---
@app.route('/')
def root():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/project')
def project():
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr
    is_admin = user_ip in admin_ips
    projects = load_projects()
    return render_template('project.html', projects=projects.keys(), is_admin=is_admin)


@app.route('/add_project', methods=['POST'])
def add_project():
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr
    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    project_name = data.get("name", "").strip()
    github_link = data.get("link", "").strip()

    if not project_name or not github_link:
        return jsonify({"error": "Nom ou lien manquant"}), 400

    projects = load_projects()
    if project_name in projects:
        return jsonify({"error": "Ce projet existe déjà"}), 400

    projects[project_name] = github_link
    save_projects(projects)
    return jsonify({"success": True, "url": github_link})


@app.route('/delete_project', methods=['POST'])
def delete_project():
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr
    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    project_name = data.get("name", "").strip()
    if not project_name:
        return jsonify({"error": "Nom invalide"}), 400

    projects = load_projects()
    if project_name not in projects:
        return jsonify({"error": "Ce projet n'existe pas"}), 404

    del projects[project_name]
    save_projects(projects)
    return jsonify({"success": True})


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'ressources'),
                               'icon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/soon')
def soon():
    return render_template('404.html')


@app.route('/socialmedia')
def social():
    return render_template('social.html')


# --- Nova-Life ---
NOVA_FILE = os.path.join(DATA_DIR, "nova_projects.json")
def load_nova_projects():
    if not os.path.exists(NOVA_FILE):
        return {}
    with open(NOVA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route('/nova-life')
@app.route('/project/nova-life')
def nova():
    admin_ips = load_admin_ips()
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    is_admin = user_ip in admin_ips
    projects = load_nova_projects()
    return render_template('nova.html', is_admin=is_admin, projects=projects)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


# --- MINDIX : Analyse intelligente d'erreurs Python ---
import ast

AI_UPLOAD_DIR = os.path.join(DATA_DIR, "ai_uploads")
if not os.path.exists(AI_UPLOAD_DIR):
    os.makedirs(AI_UPLOAD_DIR)


def mindix_analyze_error(tb_text: str):
    tb_lower = tb_text.lower()
    if "syntaxerror" in tb_lower:
        return ("🧩 Erreur de syntaxe", "Parenthèse, indentation ou deux-points manquants.", "Corrige la structure à la ligne indiquée.", 1)
    elif "nameerror" in tb_lower:
        return ("❓ Nom non défini", "Une variable ou fonction n’existe pas.", "Déclare-la avant de l’utiliser.", 2)
    elif "typeerror" in tb_lower:
        return ("🔢 Erreur de type", "Types incompatibles (ex: str + int).", "Utilise `type()` pour vérifier les types et adapter le code.", 3)
    elif "attributeerror" in tb_lower:
        return ("⚙️ Attribut inexistant", "Méthode ou propriété absente.", "Vérifie le type d’objet avant l’appel.", 3)
    elif "importerror" in tb_lower or "modulenotfounderror" in tb_lower:
        return ("📦 Module introuvable", "Le module importé est manquant ou mal orthographié.", "Installe-le ou corrige son nom.", 3)
    elif "filenotfounderror" in tb_lower:
        return ("📁 Fichier introuvable", "Le fichier demandé est inexistant.", "Vérifie le chemin et le nom du fichier.", 4)
    elif "zerodivisionerror" in tb_lower:
        return ("➗ Division par zéro", "Division d’un nombre par zéro.", "Assure-toi que le dénominateur soit non nul.", 4)
    else:
        return ("💥 Erreur inconnue", "Problème non identifiable automatiquement.", "Analyse la logique du code à la ligne indiquée.", 5)


def mindix_scan_all_errors(code: str, filename: str):
    """
    Analyse le code Python complet :
    - Détecte les erreurs de syntaxe via ast
    - Vérifie les erreurs courantes d'exécution (sans exécuter réellement le code utilisateur)
    - Trie les erreurs par gravité
    """
    errors = []
    lines = code.splitlines()

    # --- Étape 1 : vérification de la syntaxe globale ---
    try:
        ast.parse(code, filename)
    except SyntaxError as e:
        tb = traceback.format_exc()
        title, cause, fix, severity = mindix_analyze_error(tb)
        errors.append({
            "line": e.lineno or 0,
            "text": e.text.strip() if e.text else "",
            "title": title,
            "cause": cause,
            "fix": fix,
            "severity": severity
        })

    # --- Étape 2 : analyse statique de certains patterns connus ---
    # (Nom de variable inconnu, division par zéro, import introuvable)
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Division par zéro
        if re.search(r'/\s*0(?!\.)', stripped):
            errors.append({
                "line": i,
                "text": stripped,
                "title": "➗ Division par zéro",
                "cause": "Une division par zéro provoquerait une erreur à l’exécution.",
                "fix": "Assure-toi que le dénominateur n’est jamais nul.",
                "severity": 2
            })

        # Nom non défini (ex: print(xyz) sans xyz défini)
        if re.search(r'\bprint\(([^)]+)\)', stripped) and "''" not in stripped and '"' not in stripped:
            varname = re.findall(r'print\(([^)]+)\)', stripped)[0].strip()
            if not re.match(r'["\'].*["\']', varname) and not varname.isdigit():
                errors.append({
                    "line": i,
                    "text": stripped,
                    "title": "❓ Nom potentiellement non défini",
                    "cause": f"La variable '{varname}' semble non déclarée.",
                    "fix": "Déclare cette variable avant de l’utiliser.",
                    "severity": 3
                })

        # Import suspect (ex: import module_qui_existe_pas)
        if stripped.startswith("import ") or stripped.startswith("from "):
            module = stripped.split()[1].split(".")[0]
            try:
                __import__(module)
            except ImportError:
                errors.append({
                    "line": i,
                    "text": stripped,
                    "title": "📦 Module introuvable",
                    "cause": f"Le module '{module}' est introuvable sur le système.",
                    "fix": "Installe-le avec pip ou vérifie son orthographe.",
                    "severity": 3
                })

    # --- Étape 3 : dédoublonnage + tri par gravité ---
    seen = set()
    unique_errors = []
    for err in errors:
        key = (err["line"], err["title"])
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)

    unique_errors.sort(key=lambda e: e["severity"])
    return unique_errors




@app.route('/ai', methods=['GET', 'POST'])
@app.route('/mindix', methods=['GET', 'POST'])
def mindix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('ai.html', error="Aucun fichier sélectionné", output=None)
        file = request.files['file']
        if file.filename == '':
            return render_template('ai.html', error="Nom de fichier vide", output=None)
        if not file.filename.endswith('.py'):
            return render_template('ai.html', error="Seuls les fichiers .py sont acceptés", output=None)

        file_path = os.path.join(AI_UPLOAD_DIR, file.filename)
        file.save(file_path)

        code = open(file_path, "r", encoding="utf-8").read()

        # Analyse complète
        errors = mindix_scan_all_errors(code, file.filename)

        if not errors:
            return render_template('ai.html', output="✅ Aucun problème détecté.", error=None)

        # Génération du rapport complet
        report_html = "<h2 style='color:#60a5fa;'>🧠 Rapport MINDIX</h2>"
        for err in errors:
            report_html += f"""
            <div style='background:#1e293b; color:white; padding:12px; border-radius:8px; margin-bottom:12px;'>
                <p><b>{err["title"]}</b> — ligne {err["line"]}</p>
                <p>💡 {err["cause"]}</p>
                <p>🛠️ {err["fix"]}</p>
                <div style='background:#0f172a; color:#e2e8f0; padding:8px; border-radius:6px; font-family:monospace;'>
                    ➡ {err["text"]}
                </div>
            </div>
            """

        return render_template('ai.html', output=None, error=report_html)

    return render_template('ai.html', output=None, error=None)

# --- Lancement ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)



