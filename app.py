import os
import json
import re
import traceback
import ast
import subprocess
import shlex
from io import BytesIO
from flask import Flask, render_template, redirect, url_for, send_file, request, jsonify, abort
import requests

app = Flask(__name__)

# ----------------------------
# Configuration
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")

# Remote storage configuration (le serveur que tu as fourni)
REMOTE_STORAGE_BASE = "http://31.6.7.43:27205"
REMOTE_API_KEY = "HIDHkdhjsdHOIJSIdojofojoJODHIZYUOIdjdocjdo5z56f6s54dOPzjpJSo3dD6d4f6DE6e46f66sqD4f6s"

# Ensure data folder exists (pour admin/projects locaux)
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ----------------------------
# Utilitaires locaux (admin / projects)
# ----------------------------
def load_admin_ips():
    if not os.path.exists(ADMIN_FILE):
        return []
    with open(ADMIN_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def load_projects():
    if not os.path.exists(PROJECT_FILE):
        return {}
    with open(PROJECT_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_projects(projects):
    with open(PROJECT_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=4)

# ----------------------------
# Helpers pour remote storage
# ----------------------------
def remote_headers():
    return {"X-API-KEY": REMOTE_API_KEY}

def remote_list_files():
    """Récupère la liste depuis le stockage distant (/files)."""
    try:
        resp = requests.get(f"{REMOTE_STORAGE_BASE}/files", headers=remote_headers(), timeout=8)
        if resp.status_code == 200:
            return resp.json()
        return {"error": "remote_error", "status_code": resp.status_code, "text": resp.text}
    except requests.RequestException as e:
        return {"error": "unreachable", "detail": str(e)}

def remote_get_file(path):
    """Télécharge un fichier depuis le stockage distant (/files/<path>)."""
    url = f"{REMOTE_STORAGE_BASE}/files/{path}"
    try:
        resp = requests.get(url, headers=remote_headers(), stream=True, timeout=15)
        return resp  # caller manages status_code/content
    except requests.RequestException as e:
        return None

def remote_upload_file(path, file_stream, filename=None, method="POST"):
    """
    Envoie un fichier vers le stockage distant.
    - path: chemin relatif à envoyer (ex: 'ai_uploads/test.py')
    - file_stream: bytes-like OR file object
    - filename: si fournis, utilisé pour multipart
    - method: 'POST' ou 'PUT'
    """
    url = f"{REMOTE_STORAGE_BASE}/files/{path}"
    headers = remote_headers()
    try:
        # Si on a un nom de fichier on utilise multipart/form-data
        if filename:
            files = {"file": (filename, file_stream)}
            if method.upper() == "PUT":
                resp = requests.put(url, headers=headers, files=files, timeout=30)
            else:
                resp = requests.post(url, headers=headers, files=files, timeout=30)
        else:
            # raw body upload
            data = file_stream.read() if hasattr(file_stream, "read") else file_stream
            if method.upper() == "PUT":
                resp = requests.put(url, headers=headers, data=data, timeout=30)
            else:
                resp = requests.post(url, headers=headers, data=data, timeout=30)
        return resp
    except requests.RequestException as e:
        return None

def remote_delete_file(path):
    url = f"{REMOTE_STORAGE_BASE}/files/{path}"
    try:
        resp = requests.delete(url, headers=remote_headers(), timeout=10)
        return resp
    except requests.RequestException:
        return None

# ----------------------------
# Routes principales (pages)
# ----------------------------
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
    return send_file(os.path.join(app.root_path, 'ressources', 'icon.ico'))

@app.route('/soon')
def soon():
    return render_template('404.html')

@app.route('/socialmedia')
def social():
    return render_template('social.html')

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

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# ----------------------------
# MINDIX : Analyse intelligente pour .py, .js, .cs, .cpp, .c
# (uploads seront envoyés au stockage distant)
# ----------------------------
AI_UPLOAD_DIR = "ai_uploads"  # logical folder path on remote
ALLOWED_EXT = ('.py', '.js', '.cs', '.c', '.cpp', '.h', '.hpp')

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
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.search(r'/\s*0(?!\.)', stripped):
            errors.append({
                "line": i,
                "text": stripped,
                "title": "➗ Division par zéro",
                "cause": "Division par zéro détectée.",
                "fix": "Vérifie le dénominateur.",
                "severity": 2
            })

    seen = set()
    unique_errors = []
    for err in errors:
        key = (err["line"], err["title"])
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)
    unique_errors.sort(key=lambda e: e["severity"])
    return unique_errors

def parse_tool_output_to_errors(output_text: str):
    errors = []
    for line in output_text.splitlines():
        if not line.strip():
            continue
        m = re.search(r'[:\(](\d{1,5})[:\)]', line)
        lineno = int(m.group(1)) if m else 0
        title = "Erreur de syntaxe" if "error" in line.lower() else "Avertissement"
        errors.append({
            "line": lineno,
            "text": line.strip(),
            "title": title,
            "cause": line.strip(),
            "fix": "Vérifie la syntaxe.",
            "severity": 3 if "error" in line.lower() else 4
        })
    return errors

def heuristic_checks(code: str):
    errs = []
    if code.count('"') % 2 != 0 or code.count("'") % 2 != 0:
        errs.append({
            "line": 0,
            "text": "Chaîne non terminée.",
            "title": "Chaîne non terminée",
            "cause": "Nombre impair de guillemets détecté.",
            "fix": "Ferme les guillemets.",
            "severity": 3
        })
    if code.count("{") != code.count("}"):
        errs.append({
            "line": 0,
            "text": "Accolades non équilibrées.",
            "title": "Erreur de structure",
            "cause": "Trop ou pas assez d’accolades.",
            "fix": "Vérifie les blocs { }. ",
            "severity": 2
        })
    return errs

def check_with_tool(filepath: str, ext: str):
    try:
        if ext in (".c", ".cpp", ".h", ".hpp"):
            compiler = "g++" if ext != ".c" else "gcc"
            cmd = f"{compiler} -fsyntax-only -Wall {shlex.quote(filepath)}"
        elif ext == ".js":
            cmd = f"node --check {shlex.quote(filepath)}"
        elif ext == ".cs":
            cmd = "mcs -target:library " + shlex.quote(filepath)
        else:
            return []

        proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=10)
        out = proc.stderr + proc.stdout
        if proc.returncode != 0:
            return parse_tool_output_to_errors(out)
        return []
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return [{
            "line": 0,
            "text": "Timeout",
            "title": "Analyse trop longue",
            "cause": "Le vérificateur a pris trop de temps.",
            "fix": "Réessaie plus tard.",
            "severity": 2
        }]

def mindix_scan_file_from_content(content: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".py":
        return mindix_scan_all_errors(content, filename)

    # Pour les autres langages on doit écrire temporairement le fichier localement
    # pour que les outils (gcc/node/mcs) puissent l'analyser.
    try:
        tmp_path = os.path.join("/tmp", f"mindix_tmp_{os.getpid()}_{os.urandom(6).hex()}{ext}")
        with open(tmp_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content)
        result = check_with_tool(tmp_path, ext)
        # attempt to remove tmp
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if result is None:
            return heuristic_checks(content)
        return result or heuristic_checks(content)
    except Exception:
        return heuristic_checks(content)

@app.route('/mindix-v1.2', methods=['GET', 'POST'])
@app.route('/ai', methods=['GET', 'POST'])
@app.route('/mindix', methods=['GET', 'POST'])
def mindix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('ai.html', error="Aucun fichier sélectionné", output=None)
        file = request.files['file']
        if file.filename == '':
            return render_template('ai.html', error="Nom de fichier vide", output=None)

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return render_template('ai.html', error="Formats acceptés : .py, .js, .cs, .c, .cpp, .h, .hpp", output=None)

        # Lecture du contenu en mémoire (pour analyse)
        content = file.read().decode('utf-8', errors='replace')
        errors = mindix_scan_file_from_content(content, file.filename)

        # Upload du fichier vers le stockage distant (chemin : ai_uploads/<filename>)
        remote_path = f"ai_uploads/{file.filename}"
        # recreate a bytes stream for upload (requests expects bytes/file)
        stream_for_upload = BytesIO(content.encode('utf-8'))
        upload_resp = remote_upload_file(remote_path, stream_for_upload, filename=file.filename, method="POST")

        if upload_resp is None:
            upload_msg = "<p style='color:orange;'>⚠️ Échec de l'upload vers le stockage distant (injoignable).</p>"
        else:
            if upload_resp.status_code in (200, 201):
                upload_msg = "<p style='color:green;'>✅ Fichier envoyé au stockage distant.</p>"
            else:
                upload_msg = f"<p style='color:red;'>❌ Erreur lors de l'upload distant : {upload_resp.status_code} - {upload_resp.text}</p>"

        if not errors:
            return render_template('ai.html', output=f"✅ Aucun problème détecté.<br/>{upload_msg}", error=None)

        report_html = "<h2 style='color:#60a5fa;'>🧠 Rapport MINDIX</h2>"
        for err in errors:
            report_html += f"""
            <div style='background:#1e293b; color:white; padding:12px; border-radius:8px; margin-bottom:12px;'>
                <p><b>{err.get('title','Erreur')}</b> — ligne {err.get('line',0)}</p>
                <p>💡 {err.get('cause','')}</p>
                <p>🛠️ {err.get('fix','')}</p>
                <div style='background:#0f172a; color:#e2e8f0; padding:8px; border-radius:6px; font-family:monospace;'>
                    ➡ {err.get('text','')}
                </div>
            </div>
            """

        # inclure le résultat de l'upload
        report_html = upload_msg + report_html
        return render_template('ai.html', output=None, error=report_html)

    return render_template('ai.html', output=None, error=None)

# ----------------------------
# Endpoints utilitaires pour frontend pour afficher / télécharger / supprimer fichiers distants
# (optionnel: utilisés depuis l'interface si tu veux lister / récupérer / supprimer)
# ----------------------------
@app.route('/files_remote/list', methods=['GET'])
def files_remote_list():
    resp = remote_list_files()
    return jsonify(resp)

@app.route('/files_remote/get/<path:filepath>', methods=['GET'])
def files_remote_get(filepath):
    # Proxifie la récupération du fichier distant et renvoie le contenu au client
    resp = remote_get_file(filepath)
    if resp is None:
        return jsonify({"error": "Storage unreachable"}), 503
    if resp.status_code == 200:
        # recupère le contenu et le type
        buf = BytesIO(resp.content)
        # essaye d'extraire un filename depuis les headers sinon utiliser le dernier segment
        fname = None
        cd = resp.headers.get('content-disposition')
        if cd:
            m = re.search(r'filename="?([^";]+)"?', cd)
            if m:
                fname = m.group(1)
        if not fname:
            fname = os.path.basename(filepath)
        return send_file(buf, as_attachment=True, download_name=fname)
    return jsonify({"error": "remote_error", "status_code": resp.status_code, "text": resp.text}), resp.status_code

@app.route('/files_remote/delete', methods=['POST'])
def files_remote_delete():
    data = request.get_json() or {}
    path = data.get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    resp = remote_delete_file(path)
    if resp is None:
        return jsonify({"error": "Storage unreachable"}), 503
    return (resp.text, resp.status_code, resp.headers.items())

@app.route('/files_remote/upload', methods=['POST'])
def files_remote_upload_endpoint():
    """
    Endpoint pour que le frontend envoie un fichier et le stocke directement sur le stockage distant.
    Form-data: file (fichier), path (chemin relatif à utiliser, ex: ai_uploads/monfichier.py)
    """
    if 'file' not in request.files:
        return jsonify({"error": "file required"}), 400
    file = request.files['file']
    path = request.form.get('path') or f"ai_uploads/{file.filename}"
    # forward to remote
    upload_resp = remote_upload_file(path, file.stream if hasattr(file, "stream") else file, filename=file.filename, method="POST")
    if upload_resp is None:
        return jsonify({"error": "Storage unreachable"}), 503
    try:
        return (upload_resp.text, upload_resp.status_code, upload_resp.headers.items())
    except Exception:
        return jsonify({"status": "uploaded", "code": upload_resp.status_code}), upload_resp.status_code

# ----------------------------
# Run app
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = False
    print(f"App démarrée. Stockage distant : {REMOTE_STORAGE_BASE} (clé fournie).")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
