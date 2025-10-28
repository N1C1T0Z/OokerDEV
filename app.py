import os
import json
import re
import traceback
import ast
import zipfile
import tempfile
import shutil
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")
AI_UPLOAD_DIR = os.path.join(DATA_DIR, "ai_uploads")
NOVA_FILE = os.path.join(DATA_DIR, "nova_projects.json")

# --- Initialisation des dossiers ---
for folder in [DATA_DIR, AI_UPLOAD_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

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

def load_nova_projects():
    if not os.path.exists(NOVA_FILE):
        return {}
    with open(NOVA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Routes principales ---
@app.route('/')
def root():
    return redirect(url_for('home'))

@app.route('/home')
def home():
    return render_template('home.html', meta=meta)

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

@app.route('/nova-life')
@app.route('/project/nova-life')
def nova():
    admin_ips = load_admin_ips()
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    is_admin = user_ip in admin_ips
    projects = load_nova_projects()
    return render_template('nova.html', is_admin=is_admin, projects=projects)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'ressources'),
                               'icon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/socialmedia')
def social():
    return render_template('social.html', meta=meta)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# --- MINDIX analyse projet complet ---
def mindix_analyze_error(tb_text: str):
    tb_lower = tb_text.lower()
    if "syntaxerror" in tb_lower:
        return ("🧩 Erreur de syntaxe", "Parenthèse, indentation ou deux-points manquants.", "Corrige la structure à la ligne indiquée.")
    elif "nameerror" in tb_lower:
        return ("❓ Nom non défini", "Une variable ou fonction n’existe pas.", "Déclare-la avant de l’utiliser.")
    elif "importerror" in tb_lower or "modulenotfounderror" in tb_lower:
        return ("📦 Module introuvable", "Le module importé est manquant ou mal orthographié.", "Installe-le avec `pip install nom_du_module` ou corrige son nom.")
    elif "typeerror" in tb_lower:
        return ("🔢 Erreur de type", "Types incompatibles (ex: str + int).", "Utilise `type()` pour vérifier les types et adapter le code.")
    elif "attributeerror" in tb_lower:
        return ("⚙️ Attribut inexistant", "Méthode ou propriété absente.", "Vérifie le type d’objet avant l’appel.")
    elif "filenotfounderror" in tb_lower:
        return ("📁 Fichier introuvable", "Le fichier demandé est inexistant.", "Vérifie le chemin et le nom du fichier.")
    elif "zerodivisionerror" in tb_lower:
        return ("➗ Division par zéro", "Division d’un nombre par zéro.", "Assure-toi que le dénominateur soit non nul.")
    else:
        return ("💥 Erreur inconnue", "Problème non identifiable automatiquement.", "Analyse la logique du code à la ligne indiquée.")

def mindix_extract_context(tb_text: str, file_path: str):
    match = re.search(r'File ".*?%s", line (\d+)' % re.escape(os.path.basename(file_path)), tb_text)
    if not match:
        return None
    error_line = int(match.group(1))
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    start = max(0, error_line - 2)
    end = min(len(lines), error_line + 1)
    snippet = ""
    for i in range(start, end):
        line = lines[i].rstrip("\n")
        if i + 1 == error_line:
            snippet += f"➡ Ligne {i+1} : {line}  ← <b>Ici</b><br>"
        else:
            snippet += f"Ligne {i+1} : {line}<br>"
    return snippet

def scan_project(folder_path):
    py_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    return py_files

def extract_functions_classes(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    try:
        tree = ast.parse(code)
    except Exception:
        return [code]
    blocks = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            block_code = ast.get_source_segment(code, node)
            if block_code:
                blocks.append(block_code)
    if not blocks:
        blocks.append(code)
    return blocks

def test_block(code_block, file_path):
    try:
        compile(code_block, file_path, 'exec')
        return None
    except Exception:
        tb = traceback.format_exc()
        title, cause, fix = mindix_analyze_error(tb)
        snippet = mindix_extract_context(tb, file_path)
        return {"title": title, "cause": cause, "fix": fix, "snippet": snippet}

def test_full_file(file_path):
    try:
        code = open(file_path, "r", encoding="utf-8").read()
        compile(code, file_path, 'exec')
        return None
    except Exception:
        tb = traceback.format_exc()
        title, cause, fix = mindix_analyze_error(tb)
        snippet = mindix_extract_context(tb, file_path)
        return {"title": title, "cause": cause, "fix": fix, "snippet": snippet, "file": file_path, "block_number": "Full File"}

def generate_project_report_complete(folder_path):
    py_files = scan_project(folder_path)
    report = []
    for file in py_files:
        blocks = extract_functions_classes(file)
        for i, block in enumerate(blocks):
            result = test_block(block, file)
            if result:
                result["file"] = file
                result["block_number"] = i + 1
                report.append(result)
        full_result = test_full_file(file)
        if full_result:
            report.append(full_result)
    return report

@app.route('/ai', methods=['GET', 'POST'])
@app.route('/mindix', methods=['GET', 'POST'])
def mindix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('ai.html', error="Aucun fichier sélectionné", output=None)
        file = request.files['file']
        if file.filename == '':
            return render_template('ai.html', error="Nom de fichier vide", output=None)

        # Gestion zip ou py
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, file.filename)
        file.save(file_path)

        report = []
        if file.filename.endswith(".py"):
            # Analyse simple fichier unique
            result = test_block(open(file_path, "r", encoding="utf-8").read(), file_path)
            if result:
                report.append(result)
        elif file.filename.endswith(".zip"):
            # Analyse projet complet
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            report = generate_project_report_complete(temp_dir)

        shutil.rmtree(temp_dir)
        return render_template('ai.html', report=report)

    return render_template('ai.html', report=None)

# --- Lancement ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
