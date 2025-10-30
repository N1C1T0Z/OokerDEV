import os
import json
import re
import traceback
import ast
import zipfile
import tarfile
import tempfile
import requests
import subprocess
import shlex
from io import BytesIO
from flask import Flask, render_template, redirect, url_for, request, jsonify, send_file, abort, send_from_directory

# Ajouts pour l'email de vérification
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode
import uuid

app = Flask(__name__)

# ----------------------------
# Configuration générale
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")
NOVA_FILE = os.path.join(DATA_DIR, "nova_projects.json")
USERS_FILE_PATH = "data/users.json"  # chemin logique pour stockage distant

# Remote storage configuration (serveur fourni)
REMOTE_STORAGE_BASE = "http://31.6.7.43:27205"
REMOTE_API_KEY = "HIDHkdhjsdHOIJSIdojofojoJODHIZYUOIdjdocjdo5z56f6s54dOPzjpJSo3dD6d4f6DE6e46f66sqD4f6s"

# ----------------------------
# Configuration email (LWS Webmail) - **à configurer**
# ----------------------------
SMTP_SERVER = "mail.ookerdev.site"
SMTP_PORT = 465
SMTP_USER = "support@ookerdev.site"
SMTP_PASS = "HAOSDh!J2e"
VERIFY_BASE_URL = "https://ookerdev.site/verify"

# Create local data dir if missing
os.makedirs(DATA_DIR, exist_ok=True)

# ----------------------------
# Utilitaires locaux (admin / projects / nova)
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

def load_nova_projects():
    if not os.path.exists(NOVA_FILE):
        return {}
    with open(NOVA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

# ----------------------------
# Helpers pour le stockage distant (/files/...)
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
        return resp  # caller checks status_code and content
    except requests.RequestException as e:
        return None

def remote_upload_file(path, file_stream, filename=None, method="POST"):
    """
    Envoie un fichier vers le stockage distant.
    - path: chemin relatif sur le storage (ex: 'data/users.json')
    - file_stream: bytes-like ou file-like
    - filename: si fourni, utilisé pour multipart form-data (nom côté client)
    - method: 'POST' ou 'PUT'

    Spécial pour users.json : envoie le JSON pur via PUT sans multipart.
    """
    url = f"{REMOTE_STORAGE_BASE}/files/{path}"
    headers = {"X-API-KEY": REMOTE_API_KEY}

    try:
        # Si c'est users.json et PUT -> envoyer le JSON brut
        if filename == "users.json" and method.upper() == "PUT":
            data = file_stream.read() if hasattr(file_stream, "read") else file_stream
            resp = requests.put(url, headers=headers, data=data, timeout=30)
        else:
            # Autres fichiers
            if filename:
                files = {"file": (filename, file_stream)}
                if method.upper() == "PUT":
                    resp = requests.put(url, headers=headers, files=files, timeout=30)
                else:
                    resp = requests.post(url, headers=headers, files=files, timeout=30)
            else:
                data = file_stream.read() if hasattr(file_stream, "read") else file_stream
                if method.upper() == "PUT":
                    resp = requests.put(url, headers=headers, data=data, timeout=30)
                else:
                    resp = requests.post(url, headers=headers, data=data, timeout=30)

        print(f"[UPLOAD] {url} -> {resp.status_code}")
        return resp

    except requests.RequestException as e:
        print(f"[ERROR] Upload failed: {e}")
        return None

def remote_delete_file(path):
    url = f"{REMOTE_STORAGE_BASE}/files/{path}"
    try:
        resp = requests.delete(url, headers=remote_headers(), timeout=10)
        return resp
    except requests.RequestException:
        return None

# ----------------------------
# Fonctions MINDIX (analyse)
# ----------------------------
AI_UPLOAD_DIR = "ai_uploads"  # dossier logique sur storage distant
ALLOWED_EXT = ('.py', '.js', '.cs', '.c', '.cpp', '.h', '.hpp', '.zip', '.tar', '.gz')
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

    # dedupe & sort
    seen = set()
    unique_errors = []
    for err in errors:
        key = (err["line"], err["title"], err.get("text",""))
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)
    unique_errors.sort(key=lambda e: e.get("severity", 3))
    return unique_errors

def heuristic_checks(code: str):
    errs = []
    if code.count('"') % 2 != 0 or code.count("'") % 2 != 0:
        errs.append({"line":0,"text":"Chaîne non terminée.","title":"Chaîne non terminée","cause":"Nombre impair de guillemets détecté.","fix":"Ferme les guillemets.","severity":3})
    if code.count("{") != code.count("}"):
        errs.append({"line":0,"text":"Accolades non équilibrées.","title":"Erreur de structure","cause":"Trop ou pas assez d’accolades.","fix":"Vérifie les blocs { }.","severity":2})
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

def mindix_scan_file_from_content(content: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".py":
        return mindix_scan_all_errors(content, filename)

    # autres langages : écrire temporaire pour l'outil
    try:
        tmp_path = os.path.join(tempfile.gettempdir(), f"mindix_tmp_{os.getpid()}_{os.urandom(6).hex()}{ext}")
        with open(tmp_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content)
        result = check_with_tool(tmp_path, ext)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if result is None:
            return heuristic_checks(content)
        return result or heuristic_checks(content)
    except Exception:
        return heuristic_checks(content)

def mindix_scan_file(filepath: str, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()
    errors = []
    if ext == ".py":
        errors = mindix_scan_all_errors(code, filename) + heuristic_checks(code)
    else:
        errors = heuristic_checks(code)
    corrected = correct_code_simple(code)
    return errors, corrected

def correct_code_simple(code: str):
    corrected = code
    corrected = re.sub(r'^( *)\t', r'\1    ', corrected, flags=re.MULTILINE)
    # attempt simple bracket/paren balancing (naïf)
    if corrected.count('(') > corrected.count(')'):
        corrected += ')' * (corrected.count('(') - corrected.count(')'))
    if corrected.count('{') > corrected.count('}'):
        corrected += '}' * (corrected.count('{') - corrected.count('}'))
    for quote in ('"', "'"):
        if corrected.count(quote) % 2 != 0:
            corrected += quote
    return corrected

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

from flask import send_from_directory

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(BASE_DIR, 'ressources'),
                               'icon.ico', mimetype='image/vnd.microsoft.icon')
# ----------------------------
# Endpoints MINDIX / AI
# ----------------------------
@app.route('/mindix-v2', methods=['GET', 'POST'])
@app.route('/mindix', methods=['GET', 'POST'])
@app.route('/ai', methods=['GET', 'POST'])
def mindix():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('ai.html', error="Aucun fichier sélectionné", output=None)
        file = request.files['file']
        if file.filename == '':
            return render_template('ai.html', error="Nom de fichier vide", output=None)

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return render_template('ai.html', error="Formats acceptés : .py, .js, .cs, .c, .cpp, .h, .hpp, .zip, .tar, .gz", output=None)

        # Lecture du contenu en mémoire (pour analyse)
        content_bytes = file.read()
        try:
            content = content_bytes.decode('utf-8', errors='replace')
        except Exception:
            content = content_bytes.decode('latin-1', errors='replace')

        # Analyse
        errors = []
        if ext in AI_ALLOWED_SINGLE:
            errors = mindix_scan_file_from_content(content, file.filename)
        elif ext in AI_ALLOWED_ARCHIVE:
            # write temp archive and extract + scan all allowed files
            tmp_archive = os.path.join(tempfile.gettempdir(), file.filename)
            with open(tmp_archive, "wb") as f:
                f.write(content_bytes)
            temp_dir = extract_archive(tmp_archive)
            if not temp_dir:
                return render_template('ai.html', error="Archive invalide ou corrompue.", output=None)
            for root, _, files in os.walk(temp_dir):
                for f in files:
                    file_ext = os.path.splitext(f)[1].lower()
                    if file_ext in AI_ALLOWED_SINGLE:
                        path_full = os.path.join(root, f)
                        with open(path_full, "r", encoding="utf-8", errors="replace") as fc:
                            cf = fc.read()
                        errors += mindix_scan_file_from_content(cf, f)
            # repack corrected files later if needed (handled below)
        else:
            errors = [{"line":0,"text":"Format non supporté","title":"Format","cause":"Extension non prise en charge","fix":"Utiliser une extension acceptée","severity":4}]

        # Upload du fichier original (ou corrigé) vers stockage distant
        remote_path = f"{AI_UPLOAD_DIR}/{file.filename}"
        stream_for_upload = BytesIO(content.encode('utf-8') if isinstance(content, str) else content_bytes)
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

        # Construire rapport HTML (affiché dans ai.html)
        report_html = upload_msg + "<h2 style='color:#60a5fa;'>🧠 Rapport MINDIX</h2>"
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
        return render_template('ai.html', output=None, error=report_html)

    return render_template('ai.html', output=None, error=None)

# ----------------------------
# API pour gérer les fichiers distants (routes demandées)
# - /files_remote/list   [GET]
# - /files_remote/get/<path:filepath> [GET]
# - /files_remote/delete [POST] (protégé par IP admin)
# - /files_remote/upload [POST] (protégé par IP admin)
# Ces endpoints retournent JSON / téléchargent le fichier (get).
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
        buf = BytesIO(resp.content)
        fname = None
        cd = resp.headers.get('content-disposition')
        if cd:
            m = re.search(r'filename="?([^";]+)"?', cd)
            if m:
                fname = m.group(1)
        if not fname:
            fname = os.path.basename(filepath)
        # send_file with streaming buffer
        return send_file(buf, as_attachment=True, download_name=fname)
    return jsonify({"error": "remote_error", "status_code": resp.status_code, "text": resp.text}), resp.status_code

@app.route('/files_remote/delete', methods=['POST'])
def files_remote_delete():
    # Protégé par IP admin
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr
    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json() or {}
    path = data.get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    resp = remote_delete_file(path)
    if resp is None:
        return jsonify({"error": "Storage unreachable"}), 503
    try:
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception:
        return jsonify({"status": "deleted", "code": resp.status_code}), resp.status_code

@app.route('/files_remote/upload', methods=['POST'])
def files_remote_upload_endpoint():
    """
    Endpoint pour que le frontend envoie un fichier et le stocke sur le stockage distant.
    Form-data: file (fichier), path (chemin relatif, ex: ai_uploads/monfichier.py)
    Protégé par IP admin.
    """
    # Protégé par IP admin
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr
    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "file required"}), 400
    file = request.files['file']
    path = request.form.get('path') or f"{AI_UPLOAD_DIR}/{file.filename}"
    # forward to remote storage
    upload_resp = remote_upload_file(path, file.stream if hasattr(file, "stream") else file, filename=file.filename, method="POST")
    if upload_resp is None:
        return jsonify({"error": "Storage unreachable"}), 503
    try:
        return (upload_resp.text, upload_resp.status_code, upload_resp.headers.items())
    except Exception:
        return jsonify({"status": "uploaded", "code": upload_resp.status_code}), upload_resp.status_code

# ----------------------------
# Auth (stockage users sur le stockage distant)
# ----------------------------
def load_remote_users():
    """Lit le fichier data/users.json depuis le stockage distant."""
    resp = remote_get_file(USERS_FILE_PATH)
    if resp is None or resp.status_code != 200:
        return {}
    try:
        return json.loads(resp.content.decode('utf-8'))
    except Exception:
        return {}

def save_remote_users(users: dict):
    """
    Écrit le fichier data/users.json sur le stockage distant avec clé API.
    Retourne True si succès (200 ou 201), False sinon.
    """
    data_bytes = json.dumps(users, ensure_ascii=False, indent=4).encode('utf-8')
    stream = BytesIO(data_bytes)
    upload_resp = remote_upload_file(USERS_FILE_PATH, stream, filename="users.json", method="PUT")

    if upload_resp is None:
        print("[ERROR] Impossible de contacter le stockage distant")
        return False
    if upload_resp.status_code not in (200, 201):
        print(f"[ERROR] Stockage distant a répondu {upload_resp.status_code}: {upload_resp.text}")
        return False

    print("[SUCCESS] users.json sauvegardé sur le stockage distant")
    return True

def send_verification_request_to_storage(email, username, token):
    import requests
    try:
        response = requests.post(
            "http://<IP_DU_STOCKAGE>:27205/send_email",
            json={"to": email, "username": username, "token": token}
        )
        print("[DEBUG] Réponse stockage :", response.text)
        return response.status_code == 200
    except Exception as e:
        print("[EMAIL ERROR]", e)
        return False

@app.route('/sign')
def sign():
    """Affiche la page login/register switchable."""
    return render_template('login.html')

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not username or not password or not email:
        return jsonify({"error": "Champs manquants"}), 400

    users = load_remote_users()
    if username in users:
        return jsonify({"error": "Nom d'utilisateur déjà pris"}), 400

    verify_token = str(uuid.uuid4())
    users[username] = {
        "password": password,
        "email": email,
        "verify": False,
        "token": verify_token
    }

    if not save_remote_users(users):
        return jsonify({"error": "Erreur lors de l'enregistrement distant"}), 500

    # Envoi de l’email de vérification
    if not send_verification_email(email, username, verify_token):
        # compte créé mais mail pas envoyé
        return jsonify({"warning": "Compte créé mais email non envoyé"}), 200

    return jsonify({"success": True, "message": "Compte créé, vérifiez votre email pour activer votre compte"})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    users = load_remote_users()
    if username not in users or users[username]['password'] != password:
        return jsonify({"error": "Identifiants invalides"}), 401

    if not users[username].get('verify', False):
        return jsonify({"error": "Compte non vérifié. Consultez votre email."}), 403

    return jsonify({"success": True, "message": f"Bienvenue {username}!"})

@app.route('/verify')
def verify_email():
    token = request.args.get('token', '').strip()
    username = request.args.get('user', '').strip()
    if not token or not username:
        return "Lien invalide", 400

    users = load_remote_users()
    if username not in users:
        return "Utilisateur introuvable", 404

    if users[username].get('token') != token:
        return "Token invalide ou expiré", 400

    users[username]['verify'] = True
    users[username].pop('token', None)
    save_remote_users(users)

    return f"<h2>Email vérifié ✅</h2><p>Bonjour {username}, votre compte est maintenant activé.</p>"

# ----------------------------
# Lancement
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = False
    print(f"App démarrée. Stockage distant : {REMOTE_STORAGE_BASE} (clé fournie).")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
