from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify
import os
import json

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ADMIN_FILE = os.path.join(DATA_DIR, "admin.json")
PROJECT_FILE = os.path.join(DATA_DIR, "projects.json")

# Vérifie l'existence du dossier data
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Charger les IP admin
def load_admin_ips():
    if not os.path.exists(ADMIN_FILE):
        return []
    with open(ADMIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Charger les projets
def load_projects():
    if not os.path.exists(PROJECT_FILE):
        return {}
    with open(PROJECT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Sauvegarder les projets
def save_projects(projects):
    with open(PROJECT_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=4)

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

    # Pas de route créée : on renvoie directement le lien
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

NOVA_FILE = os.path.join(BASE_DIR, "data/nova_projects.json")

def load_nova_projects():
    if not os.path.exists(NOVA_FILE):
        return {}  # retourne un dict vide si aucun fichier
    with open(NOVA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)  # doit être un dict : { "NomProjet": { "link": "...", "description": "...", "tags": [...] } }

@app.route('/nova-life')
@app.route('/project/nova-life')
def nova():
    admin_ips = load_admin_ips()
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    is_admin = user_ip in admin_ips

    projects = load_nova_projects()  # <-- on fournit maintenant la variable
    return render_template('nova.html', is_admin=is_admin, projects=projects)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

import traceback

AI_UPLOAD_DIR = os.path.join(BASE_DIR, "data/ai_uploads")
if not os.path.exists(AI_UPLOAD_DIR):
    os.makedirs(AI_UPLOAD_DIR)

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

        # Lire et exécuter le code
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            
            # Exécution dans un namespace limité
            local_vars = {}
            exec(code, {"__builtins__": {}}, local_vars)

            output = "Code exécuté sans erreurs."
            return render_template('ai.html', output=output, error=None)
        except Exception as e:
            tb = traceback.format_exc()
            return render_template('ai.html', output=None, error=tb)
    
    # GET request
    return render_template('ai.html', output=None, error=None)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)





