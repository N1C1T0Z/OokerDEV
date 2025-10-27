from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify
import os
import json

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "project")
ADMIN_FILE = os.path.join(BASE_DIR, "data/admin.json")

# Charger les IP admin
def load_admin_ips():
    if not os.path.exists(ADMIN_FILE):
        return []
    with open(ADMIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

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

    if not os.path.exists(PROJECT_TEMPLATE_DIR):
        os.makedirs(PROJECT_TEMPLATE_DIR)

    files = [f[:-5] for f in os.listdir(PROJECT_TEMPLATE_DIR) if f.endswith('.html')]

    return render_template('project.html', projects=files, is_admin=is_admin)

@app.route('/project/<name>')
def project_page(name):
    path = os.path.join(PROJECT_TEMPLATE_DIR, f"{name}.html")
    if os.path.exists(path):
        return render_template(f"project/{name}.html")
    else:
        return render_template('home.html', custom_message="404 - Projet introuvable"), 404

@app.route('/add_project', methods=['POST'])
def add_project():
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr

    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    project_name = data.get("name", "").strip().lower()

    if not project_name or "/" in project_name or " " in project_name:
        return jsonify({"error": "Nom invalide"}), 400

    path = os.path.join(PROJECT_TEMPLATE_DIR, f"{project_name}.html")
    if os.path.exists(path):
        return jsonify({"error": "Ce projet existe déjà"}), 400

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{project_name.capitalize()} - Ooker Dev</title>
    <link rel="stylesheet" href="{{{{ url_for('static', filename='styles.css') }}}}">
</head>
<body>
    <header class="navbar">
        <div class="logo-text">Ooker Dev</div>
    </header>
    <main class="hero">
        <h1>404</h1>
        <p>Le contenu de ce projet n’a pas encore été ajouté.</p>
    </main>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return jsonify({"success": True, "url": f"/project/{project_name}"})


@app.route('/delete_project', methods=['POST'])
def delete_project():
    admin_ips = load_admin_ips()
    user_ip = request.remote_addr

    if user_ip not in admin_ips:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    project_name = data.get("name", "").strip().lower()

    if not project_name:
        return jsonify({"error": "Nom invalide"}), 400

    path = os.path.join(PROJECT_TEMPLATE_DIR, f"{project_name}.html")
    if not os.path.exists(path):
        return jsonify({"error": "Ce projet n'existe pas"}), 404

    os.remove(path)
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

@app.route('/nova-life')
def nova():
    return render_template('nova.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

