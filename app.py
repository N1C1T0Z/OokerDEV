import os
import json
import re
import traceback
import ast
import zipfile
import tarfile
import tempfile
import requests
from flask import Flask, render_template, redirect, url_for, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")

os.makedirs(DATA_DIR, exist_ok=True)

# --- Serveur distant ---
SERVER_URL = "http://31.6.7.43:27205"
API_KEY = "HIDHkdhjsdHOIJSIdojofojoJODHIZYUOIdjdocjdo5z56f6s54dOPzjpJSo3dD6d4f6DE6e46f66sqD4f6s"
HEADERS = {"X-API-KEY": API_KEY}

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

# --- Fonctions de communication avec le serveur distant ---
def upload_file_to_remote(file_path, remote_name=None):
    remote_name = remote_name or os.path.basename(file_path)
    with open(file_path, "rb") as f:
        r = requests.post(f"{SERVER_URL}/upload/{remote_name}", headers=HEADERS, files={"file": f})
    return r.status_code == 200

def download_file_from_remote(filename):
    r = requests.get(f"{SERVER_URL}/download/{filename}", headers=HEADERS, stream=True)
    if r.status_code == 200:
        temp_path = os.path.join(tempfile.gettempdir(), filename)
        with open(temp_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return temp_path
    return None

def delete_file_from_remote(filename):
    r = requests.delete(f"{SERVER_URL}/delete/{filename}", headers=HEADERS)
    return r.status_code == 200

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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# ----------------------------
# Nova-Life (conserve la logique)
# ----------------------------
NOVA_FILE = os.path.join(DATA_DIR, "nova_projects.json")
def load_nova_projects():
    if not os.path.exists(NOVA_FILE):
        return {}
    with open(NOVA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

@app.route('/nova-life')
@app.route('/project/nova-life')
def nova():
    admin_ips = load_admin_ips()
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    is_admin = user_ip in admin_ips
    projects = load_nova_projects()
    return render_template('nova.html', is_admin=is_admin, projects=projects)

# --- MINDIX : Analyse et correction ---
AI_ALLOWED_SINGLE = ('.py', '.js', '.cs', '.c', '.cpp', '.h', '.hpp')
AI_ALLOWED_ARCHIVE = ('.zip', '.tar', '.gz')

def mindix_analyze_error(tb_text: str):
    tb_lower = tb_text.lower()
    if "syntaxerror" in tb_lower:
        return ("🧩 Erreur de syntaxe", "Parenthèse, indentation ou deux-points manquants.", "Corrige la structure à la ligne indiquée.", 1)
    elif "nameerror" in tb_lower:
        return ("❓ Nom non défini", "Une variable ou fonction n’existe pas.", "Déclare-la avant de l’utiliser.", 2)
    elif "typeerror" in tb_lower:
        return ("🔢 Erreur de type", "Types incompatibles (ex: str + int).", "Utilise `type()` pour vérifier les types.", 3)
    elif "attributeerror" in tb_lower:
        return ("⚙️ Attribut inexistant", "Méthode ou propriété absente.", "Vérifie le type d’objet avant l’appel.", 3)
    elif "importerror" in tb_lower or "modulenotfounderror" in tb_lower:
        return ("📦 Module introuvable", "Le module importé est manquant.", "Installe-le ou corrige son nom.", 3)
    elif "filenotfounderror" in tb_lower:
        return ("📁 Fichier introuvable", "Le fichier demandé est inexistant.", "Vérifie le chemin et le nom du fichier.", 4)
    elif "zerodivisionerror" in tb_lower:
        return ("➗ Division par zéro", "Division d’un nombre par zéro.", "Assure-toi que le dénominateur soit non nul.", 4)
    else:
        return ("💥 Erreur inconnue", "Problème non identifiable.", "Analyse la logique du code à la ligne indiquée.", 5)

def mindix_scan_all_errors(code: str, filename: str):
    errors = []
    lines = code.splitlines()
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

    for i, line in enumerate(lines, 1):
        if re.search(r'/\s*0(?!\.)', line):
            errors.append({
                "line": i,
                "text": line.strip(),
                "title": "➗ Division par zéro",
                "cause": "Division par zéro détectée.",
                "fix": "Vérifie le dénominateur.",
                "severity": 2
            })
    return errors

def heuristic_checks(code: str):
    errs = []
    if code.count('"') % 2 != 0 or code.count("'") % 2 != 0:
        errs.append({"line":0,"text":"Chaîne non terminée.","title":"Chaîne non terminée","cause":"Nombre impair de guillemets détecté.","fix":"Ferme les guillemets.","severity":3})
    if code.count("{") != code.count("}"):
        errs.append({"line":0,"text":"Accolades non équilibrées.","title":"Erreur de structure","cause":"Trop ou pas assez d’accolades.","fix":"Vérifie les blocs { }.","severity":2})
    return errs

def correct_code(code: str):
    corrected = code
    corrected = re.sub(r'^( *)\t', r'\1    ', corrected, flags=re.MULTILINE)
    if corrected.count('(') > corrected.count(')'):
        corrected += ')' * (corrected.count('(') - corrected.count(')'))
    if corrected.count(')') > corrected.count('('):
        corrected = '(' * (corrected.count(')') - corrected.count('(')) + corrected
    if corrected.count('{') > corrected.count('}'):
        corrected += '}' * (corrected.count('{') - corrected.count('}'))
    if corrected.count('}') > corrected.count('{'):
        corrected = '{' * (corrected.count('}') - corrected.count('{')) + corrected
    for quote in ('"', "'"):
        if corrected.count(quote) % 2 != 0:
            corrected += quote
    return corrected

def mindix_scan_file(filepath: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()
    errors = []
    if ext == ".py":
        errors = mindix_scan_all_errors(code, filename) + heuristic_checks(code)
    else:
        errors = heuristic_checks(code)
    corrected = correct_code(code)
    return errors, corrected

def extract_archive(file_path):
    temp_dir = tempfile.mkdtemp()
    try:
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        elif tarfile.is_tarfile(file_path):
            with tarfile.open(file_path, 'r:*') as tar_ref:
                tar_ref.extractall(temp_dir)
        else:
            return None
    except Exception:
        return None
    return temp_dir

def repackage_files(directory, original_filename):
    zip_path = os.path.join(tempfile.gettempdir(), f"corrected_{original_filename}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(directory):
            for f in files:
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, directory)
                zipf.write(full_path, arcname)
    return zip_path

# --- Routes MINDIX ---
@app.route('/ai', methods=['GET','POST'])
@app.route('/mindix-v2', methods=['GET','POST'])
@app.route('/mindix', methods=['GET','POST'])
def mindix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('ai.html', error="Aucun fichier sélectionné", output=None, download_link=None)
        file = request.files['file']
        if file.filename == '':
            return render_template('ai.html', error="Nom de fichier vide", output=None, download_link=None)

        filename = file.filename
        temp_local = os.path.join(tempfile.gettempdir(), filename)
        file.save(temp_local)

        ext = os.path.splitext(filename)[1].lower()
        report_html = ""
        download_link = None

        if ext in AI_ALLOWED_SINGLE:
            errors, corrected = mindix_scan_file(temp_local, filename)
            corrected_path = os.path.join(tempfile.gettempdir(), f"corrected_{filename}")
            with open(corrected_path, 'w', encoding='utf-8') as f:
                f.write(corrected)
            upload_file_to_remote(corrected_path, f"corrected_{filename}")
            download_link = f"{SERVER_URL}/download/corrected_{filename}?api_key={API_KEY}"

            if errors:
                for err in errors:
                    report_html += f"<div style='background:#1e293b; color:white; padding:12px; border-radius:8px; margin-bottom:12px;'>"
                    report_html += f"<p><b>{err['title']}</b> — ligne {err['line']}</p>"
                    report_html += f"<p>💡 {err['cause']}</p>"
                    report_html += f"<p>🛠️ {err['fix']}</p>"
                    report_html += f"<div style='background:#0f172a; color:#e2e8f0; padding:8px; border-radius:6px; font-family:monospace;'>➡ {err['text']}</div></div>"
            else:
                report_html = "✅ Aucun problème détecté."

        elif ext in AI_ALLOWED_ARCHIVE:
            temp_dir = extract_archive(temp_local)
            if not temp_dir:
                return render_template('ai.html', error="Archive invalide ou corrompue.", output=None, download_link=None)
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    file_full = os.path.join(root, f)
                    file_ext = os.path.splitext(f)[1].lower()
                    if file_ext in AI_ALLOWED_SINGLE:
                        _, corrected = mindix_scan_file(file_full, f)
                        with open(file_full, 'w', encoding='utf-8') as fc:
                            fc.write(corrected)
            zip_corrected = repackage_files(temp_dir, filename)
            upload_file_to_remote(zip_corrected, f"corrected_{filename}.zip")
            download_link = f"{SERVER_URL}/download/corrected_{filename}.zip?api_key={API_KEY}"
            report_html = "✅ Analyse terminée. Cliquez pour télécharger l'archive corrigée."

        else:
            return render_template('ai.html', error="Format non supporté.", output=None, download_link=None)

        return render_template('ai.html', error=None, output=report_html, download_link=download_link)

    return render_template('ai.html', output=None, error=None, download_link=None)

# --- Lancement ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
