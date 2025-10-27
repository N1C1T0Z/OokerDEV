import os
import json
import traceback
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


# --- Utilitaires existants ---
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


# --- AI EXECUTOR avec analyse d'erreurs ---
AI_UPLOAD_DIR = os.path.join(DATA_DIR, "ai_uploads")
if not os.path.exists(AI_UPLOAD_DIR):
    os.makedirs(AI_UPLOAD_DIR)


def analyze_error(tb_text: str):
    """
    Analyse la trace d'erreur Python et renvoie (titre, cause, solution)
    """
    tb_lower = tb_text.lower()

    if "syntaxerror" in tb_lower:
        return (
            "🧩 Erreur de syntaxe",
            "Ton code contient une erreur de structure (parenthèse, indentation ou deux-points).",
            "Vérifie la ligne indiquée dans la trace et assure-toi que la syntaxe Python est correcte."
        )
    elif "nameerror" in tb_lower:
        return (
            "❓ Nom non défini",
            "Tu utilises une variable ou une fonction avant de l’avoir déclarée.",
            "Corrige le nom de la variable ou déclare-la avant son utilisation."
        )
    elif "importerror" in tb_lower or "modulenotfounderror" in tb_lower:
        return (
            "📦 Module introuvable",
            "Le module que tu veux importer n’existe pas ou n’est pas installé.",
            "Installe-le avec `pip install nom_du_module` ou vérifie son orthographe."
        )
    elif "typeerror" in tb_lower:
        return (
            "🔢 Erreur de type",
            "Une opération utilise des types incompatibles (ex: addition entre str et int).",
            "Vérifie les types avec `print(type(variable))` et adapte ton code."
        )
    elif "attributeerror" in tb_lower:
        return (
            "⚙️ Attribut inexistant",
            "Tu appelles une méthode ou propriété qui n’existe pas sur cet objet.",
            "Vérifie le type d’objet avant d’utiliser ses méthodes."
        )
    elif "zerodivisionerror" in tb_lower:
        return (
            "➗ Division par zéro",
            "Le code tente de diviser un nombre par zéro.",
            "Assure-toi que le dénominateur n’est jamais égal à zéro."
        )
    elif "file not found" in tb_lower or "filenotfounderror" in tb_lower:
        return (
            "📁 Fichier introuvable",
            "Le script tente d’ouvrir un fichier qui n’existe pas.",
            "Vérifie que le chemin et le nom du fichier sont corrects."
        )
    else:
        return (
            "💥 Erreur inconnue",
            "L’analyse automatique n’a pas pu identifier précisément la cause.",
            "Lis la trace complète ci-dessous pour repérer la ligne fautive."
        )


@app.route('/ai', methods=['GET', 'POST'])
def ai():
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

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            
            # Exécution dans un environnement isolé
            local_vars = {}
            exec(code, {"__builtins__": {}}, local_vars)

            output = "✅ Code exécuté sans erreurs."
            return render_template('ai.html', output=output, error=None)
        except Exception:
            tb = traceback.format_exc()
            title, cause, fix = analyze_error(tb)
            detailed = f"{title}\n\n💡 **Cause probable :** {cause}\n\n🛠️ **Comment corriger :** {fix}\n\n---\n📜 **Trace complète :**\n{tb}"
            return render_template('ai.html', output=None, error=detailed)

    return render_template('ai.html', output=None, error=None)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
