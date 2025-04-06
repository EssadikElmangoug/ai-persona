from flask import Flask, request, render_template, send_file, jsonify, redirect, url_for, session, flash
from gemini import get_ollama_response, get_ollama_models
from speechToText import conver_to_audio
from database import save_settings, get_settings, get_all_projects, get_project_by_id, update_project, delete_project
from database import create_admin_user, get_user, verify_user, users_collection
import json
import os
import secrets
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps

# User model for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['_id']
        self.username = user_data['username']
        self.is_admin = user_data.get('is_admin', False)
    
    @staticmethod
    def get(user_id):
        user_data = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user_data:
            return None
        user_data['_id'] = str(user_data['_id'])
        return User(user_data)

# from app import AIGirlfriend
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(16))

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access the dashboard'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Admin-only decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need admin privileges to access this page')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = verify_user(username, password)
        
        if user_data:
            user = User(user_data)
            login_user(user)
            
            # Get the next parameter if it exists
            next_page = request.args.get('next')
            
            # Redirect to the next page or dashboard
            if next_page:
                return redirect(next_page)
            else:
                return redirect(url_for('dashboard'))
        else:
            error = 'Invalid username or password'
    
    return render_template('login.html', error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route("/setup", methods=["GET", "POST"])
def setup():
    # Check if any admin users already exist
    admin_exists = users_collection.find_one({'is_admin': True})
    if admin_exists:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        setup_code = request.form.get('setup_code')
        
        # Simple validations
        if len(password) < 8:
            return render_template('setup.html', error='Password must be at least 8 characters long')
        
        if password != confirm_password:
            return render_template('setup.html', error='Passwords do not match')
        
        # Verify setup code
        expected_setup_code = os.getenv('SETUP_CODE')
        if not expected_setup_code or setup_code != expected_setup_code:
            return render_template('setup.html', error='Invalid setup code')
        
        # Create admin user
        result = create_admin_user(username, password)
        
        if result['success']:
            return render_template('setup.html', success='Admin account created successfully!')
        else:
            return render_template('setup.html', error=result['message'])
    
    return render_template('setup.html')

@app.route("/tts", methods=["POST"])
def tts():
    messages = request.form.get("messages")
    
    # Get model from request if available, otherwise check database settings
    requested_model = request.form.get("model")
    page_title = request.form.get("title")  # Get the title/id to look up settings
    
    if requested_model:
        model = requested_model
    else:
        # Try to get from database settings
        settings = get_settings(page_title)
        if settings and settings.get('model_selection'):
            model = settings.get('model_selection')
        else:
            # Fallback to default model
            model = "llama3.2:3b"
    
    messages = json.loads(messages)
    messages = get_ollama_response(messages, model)
    return jsonify({"message": messages})

@app.route("/dashboard", methods=["GET"])
@login_required
@admin_required
def dashboard():
    # Get current settings from database
    settings = get_settings()
    return render_template('dashboard.html', settings=settings)

@app.route("/update_settings", methods=["POST"])
@login_required
@admin_required
def update_settings():
    try:
        page_title = request.form.get("pageTitle")
        system_prompt = request.form.get("systemPrompt")
        model_selection = request.form.get("modelSelection")
        use_custom_avatar = request.form.get("useCustomAvatar") == "true"
        
        # Validate required fields
        if not page_title or not system_prompt or not model_selection:
            return jsonify({
                "success": False,
                "message": "All fields are required. Please complete the form."
            }), 400
        
        # Handle avatar file upload
        avatar_path = '/static/uploads/default.png'  # Set default avatar path
        if use_custom_avatar and 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename:
                # Create uploads directory if it doesn't exist
                upload_dir = os.path.join(app.static_folder, 'uploads')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                
                # Save the file with a secure filename
                filename = secure_filename(avatar_file.filename)
                file_path = os.path.join(upload_dir, filename)
                avatar_file.save(file_path)
                
                # Store the relative path to be saved in database/config
                avatar_path = f'/static/uploads/{filename}'
        
        # Create a slug from the page title (ensures it's URL-friendly)
        title_slug = page_title.replace(' ', '-').lower() if page_title else None
        
        # Save settings to MongoDB, now using the title slug as primary key
        result = save_settings(
            page_title=title_slug,
            system_prompt=system_prompt,
            model_selection=model_selection,
            avatar_path=avatar_path
        )
        
        # Check if the operation was successful
        if result['success']:
            return jsonify({
                "success": True, 
                "message": "Settings updated successfully",
                "avatar_path": avatar_path,
                "settings_id": result['settings_id'],
                "redirect_url": f"/d/{title_slug}"  # Add redirect URL to the response
            })
        else:
            # If we got an error about duplicate title
            if result.get('error') == 'duplicate_title':
                return jsonify({
                    "success": False, 
                    "message": "This project already exists. Please choose a different title.",
                    "error": "duplicate_title"
                }), 409  # HTTP 409 Conflict status code
            else:
                return jsonify({"success": False, "message": result.get('message', "Unknown error")})
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/get-models", methods=["GET"])
def get_models():
    models = get_ollama_models()
    return jsonify({"models": models})

@app.route("/get-settings", methods=["GET"])
def get_current_settings():
    # Get page_title from query parameters if provided
    page_title = request.args.get("title")
    
    # If page_title is provided, get specific settings
    if page_title:
        settings = get_settings(page_title)
        if settings:
            return jsonify({"success": True, "settings": settings})
        else:
            return jsonify({"success": False, "message": f"No settings found for project: {page_title}"})
    else:
        # If no page_title is provided, get the first project (default behavior)
        settings = get_settings()
        if settings:
            return jsonify({"success": True, "settings": settings})
        else:
            return jsonify({"success": False, "message": "No settings found"})

@app.route("/d/<id>", methods=["GET"])
def ai(id):
    # Use the ID (which is now the title slug) to get settings
    settings = get_settings(id)
    if settings:
        # Get avatar path from settings or use default
        avatar_path = settings.get('avatar_path')
        if not avatar_path:
            # Default avatar path
            avatar_path = "/static/uploads/default.png"
            
        # Render the project template with settings
        return render_template('project.html', settings=settings, avatar_path=avatar_path)
    else:
        return "AI project not found", 404

@app.route("/get-all-projects", methods=["GET"])
@login_required
@admin_required
def fetch_all_projects():
    """Route to get all projects from the database"""
    try:
        projects = get_all_projects()
        return jsonify({"success": True, "projects": projects})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/get-project/<project_id>", methods=["GET"])
@login_required
@admin_required
def fetch_project(project_id):
    """Route to get a single project by ID"""
    try:
        project = get_project_by_id(project_id)
        if project:
            return jsonify({"success": True, "project": project})
        else:
            return jsonify({"success": False, "message": "Project not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/delete-project/<project_id>", methods=["DELETE"])
@login_required
@admin_required
def remove_project(project_id):
    """Route to delete a project by ID"""
    try:
        result = delete_project(project_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/edit-project/<project_id>", methods=["GET"])
@login_required
@admin_required
def edit_project_page(project_id):
    """Route to render the edit project page"""
    project = get_project_by_id(project_id)
    if project:
        return render_template('edit-project.html', project=project)
    else:
        return "Project not found", 404

@app.route("/update_project", methods=["POST"])
@login_required
@admin_required
def update_project_settings():
    """Route to update an existing project"""
    try:
        # Get the current project ID
        project_id = request.form.get("projectId")
        page_title = request.form.get("pageTitle")
        system_prompt = request.form.get("systemPrompt")
        model_selection = request.form.get("modelSelection")
        avatar_option = request.form.get("avatarOption")
        
        # Validate required fields
        if not project_id or not page_title or not system_prompt or not model_selection:
            return jsonify({
                "success": False,
                "message": "All fields are required. Please complete the form."
            }), 400
        
        # Check if the project exists
        existing_project = get_project_by_id(project_id)
        if not existing_project:
            return jsonify({
                "success": False,
                "message": f"Project '{project_id}' not found"
            }), 404
        
        # Handle avatar updates based on selected option
        avatar_path = existing_project.get('avatar_path')
        
        if avatar_option == 'upload' and 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename:
                # Create uploads directory if it doesn't exist
                upload_dir = os.path.join(app.static_folder, 'uploads')
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                
                # Save the file with a secure filename
                filename = secure_filename(avatar_file.filename)
                file_path = os.path.join(upload_dir, filename)
                avatar_file.save(file_path)
                
                # Store the relative path to be saved in database/config
                avatar_path = f'/static/uploads/{filename}'
        elif avatar_option == 'default':
            # Use default avatar
            avatar_path = '/static/uploads/default.png'
        # For 'keep' option, we use the existing avatar_path value
        
        # Create a slug from the page title if it changed
        new_title_slug = None
        if page_title:
            # Convert to slug format first
            page_title_slug = page_title.replace(' ', '-').lower()
            # Only set new title if it's different from current
            if page_title_slug != project_id:
                new_title_slug = page_title_slug
        
        # Update the project in the database
        result = update_project(
            page_title=project_id,
            new_title=new_title_slug,
            system_prompt=system_prompt,
            model_selection=model_selection,
            avatar_path=avatar_path
        )
        
        # Check if the operation was successful
        if result['success']:
            # Get the new page title (might be the same as before)
            new_page_title = result.get('new_page_title', project_id)
            
            return jsonify({
                "success": True, 
                "message": "Project updated successfully",
                "redirect_url": f"/d/{new_page_title}" 
            })
        else:
            # Handle specific errors
            if result.get('error') == 'duplicate_title':
                return jsonify({
                    "success": False, 
                    "message": "A project with this title already exists. Please choose a different title.",
                    "error": "duplicate_title"
                }), 409
            else:
                return jsonify({
                    "success": False, 
                    "message": result.get('message', "Unknown error")
                })
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    from dotenv import load_dotenv
    from bson import ObjectId
    load_dotenv()
    
    # Add a SETUP_CODE to your .env file to secure the initial admin setup
    if not os.getenv('SETUP_CODE'):
        setup_code = secrets.token_hex(6)
        print(f"No SETUP_CODE found in .env. Using generated code: {setup_code}")
        print(f"Add this to your .env file: SETUP_CODE={setup_code}")
        os.environ['SETUP_CODE'] = setup_code
        
    # Generate a SECRET_KEY if not already set
    if not os.getenv('SECRET_KEY'):
        secret_key = secrets.token_hex(16)
        print(f"No SECRET_KEY found in .env. Using generated key: {secret_key}")
        print(f"Add this to your .env file: SECRET_KEY={secret_key}")
        os.environ['SECRET_KEY'] = secret_key
        
    app.run('0.0.0.0', debug=True)