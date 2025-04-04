from flask import Flask, request, render_template, send_file, jsonify
from gemini import get_ollama_response, get_ollama_models
from speechToText import conver_to_audio
from database import save_settings, get_settings, get_all_projects, get_project_by_id, update_project, delete_project
import json
import os
from werkzeug.utils import secure_filename
# from app import AIGirlfriend
app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

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
def dashboard():
    # Get current settings from database
    settings = get_settings()
    return render_template('dashboard.html', settings=settings)

@app.route("/update_settings", methods=["POST"])
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
                "redirect_url": f"/ai/{title_slug}"  # Add redirect URL to the response
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
    
    settings = get_settings(page_title)
    if settings:
        return jsonify({"success": True, "settings": settings})
    else:
        return jsonify({"success": False, "message": "No settings found"})

@app.route("/ai/<id>", methods=["GET"])
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
def fetch_all_projects():
    """Route to get all projects from the database"""
    try:
        projects = get_all_projects()
        return jsonify({"success": True, "projects": projects})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/get-project/<project_id>", methods=["GET"])
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
def remove_project(project_id):
    """Route to delete a project by ID"""
    try:
        result = delete_project(project_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/edit-project/<project_id>", methods=["GET"])
def edit_project_page(project_id):
    """Route to render the edit project page"""
    project = get_project_by_id(project_id)
    if project:
        return render_template('edit-project.html', project=project)
    else:
        return "Project not found", 404

@app.route("/update_project", methods=["POST"])
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
                "redirect_url": f"/ai/{new_page_title}" 
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
    load_dotenv()
    app.run('0.0.0.0', debug=True)