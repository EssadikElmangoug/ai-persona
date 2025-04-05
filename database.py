from pymongo import MongoClient
import os
from dotenv import load_dotenv
from bson import ObjectId

# Load environment variables
load_dotenv()

# Get MongoDB connection string from environment variables
# Default to a local MongoDB instance if not provided
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')

# Initialize MongoDB client
client = MongoClient(MONGO_URI)

# Define database
db = client['project_db']

# Define collections
settings_collection = db['settings']

def save_settings(page_title=None, system_prompt=None, 
                  model_selection=None, avatar_path=None):
    """
    Save user settings to MongoDB, using page_title as primary key
    
    Args:
        page_title (str): Title of the page (used as primary key)
        system_prompt (str): System prompt for the AI
        model_selection (str): Selected model name
        avatar_path (str): Path to the avatar image
        
    Returns:
        dict: Result with success status, message and ID of the document
        
    Raises:
        ValueError: If page_title is None or if a project with the same title already exists
    """
    # Check if page_title is provided
    if page_title is None:
        raise ValueError("Page title is required")
    
    # Check if a project with this title already exists
    existing_project = settings_collection.find_one({'page_title': page_title})
    if existing_project:
        # If current update is for the same document, allow the update
        return {
            'success': False,
            'message': "A project with this title already exists",
            'error': 'duplicate_title',
            'settings_id': str(existing_project['_id'])
        }
    
    settings = {
        'page_title': page_title
    }
    
    # Only add fields that are not None
    if system_prompt is not None:
        settings['system_prompt'] = system_prompt
    if model_selection is not None:
        settings['model_selection'] = model_selection
    if avatar_path is not None:
        settings['avatar_path'] = avatar_path
    
    # Insert new document with page_title as primary key
    result = settings_collection.insert_one(settings)
    
    return {
        'success': True,
        'message': "Settings saved successfully",
        'settings_id': str(result.inserted_id)
    }

def get_settings(page_title=None):
    """
    Get settings from MongoDB by page_title
    
    Args:
        page_title (str): Page title identifier
        
    Returns:
        dict: Settings document or None if not found
    """
    if page_title:
        doc = settings_collection.find_one({'page_title': page_title})
    else:
        # If no page_title provided, return the first settings document
        doc = settings_collection.find_one()
    
    if doc:
        # Convert ObjectId to string for JSON serialization
        doc['_id'] = str(doc['_id'])
        return doc
    
    return None

def get_all_projects():
    """
    Get all projects from the database
    
    Returns:
        list: List of all project documents
    """
    projects = list(settings_collection.find())
    
    # Convert ObjectId to string for JSON serialization
    for project in projects:
        project['_id'] = str(project['_id'])
    
    return projects

def get_project_by_id(page_title):
    """
    Get a specific project by page_title
    
    Args:
        page_title (str): Page title identifier
        
    Returns:
        dict: Project document or None if not found
    """
    project = settings_collection.find_one({'page_title': page_title})
    
    if project:
        # Convert ObjectId to string for JSON serialization
        project['_id'] = str(project['_id'])
        return project
    
    return None

def update_project(page_title, new_title=None, system_prompt=None, 
                  model_selection=None, avatar_path=None):
    """
    Update an existing project
    
    Args:
        page_title (str): Current page title (primary key for lookup)
        new_title (str): New title for the project (optional)
        system_prompt (str): System prompt for the AI (optional)
        model_selection (str): Selected model name (optional)
        avatar_path (str): Path to the avatar image (optional)
        
    Returns:
        dict: Result with success status, message and ID of the document
    """
    # Find the project to update
    project = settings_collection.find_one({'page_title': page_title})
    
    if not project:
        return {
            'success': False,
            'message': f"Project '{page_title}' not found",
            'error': 'not_found'
        }
    
    # Build update document with provided fields
    update_doc = {}
    
    # If a new title is provided, check it's not a duplicate
    if new_title and new_title != page_title:
        # Create slug from new title
        new_title_slug = new_title.replace(' ', '-').lower()
        
        # Check if the new title already exists
        title_exists = settings_collection.find_one({'page_title': new_title_slug})
        if title_exists:
            return {
                'success': False,
                'message': f"A project with the title '{new_title}' already exists",
                'error': 'duplicate_title'
            }
        
        update_doc['page_title'] = new_title_slug
    
    # Add other fields if provided
    if system_prompt is not None:
        update_doc['system_prompt'] = system_prompt
    if model_selection is not None:
        update_doc['model_selection'] = model_selection
    if avatar_path is not None:
        update_doc['avatar_path'] = avatar_path
    
    # Only update if there are changes
    if update_doc:
        result = settings_collection.update_one(
            {'page_title': page_title},
            {'$set': update_doc}
        )
        
        if result.modified_count > 0:
            return {
                'success': True,
                'message': "Project updated successfully",
                'new_page_title': update_doc.get('page_title', page_title)
            }
        else:
            return {
                'success': False,
                'message': "No changes were made",
                'error': 'no_changes'
            }
    else:
        return {
            'success': False,
            'message': "No update data provided",
            'error': 'no_data'
        }

def delete_project(page_title):
    """
    Delete a project by page_title
    
    Args:
        page_title (str): Page title identifier
        
    Returns:
        dict: Result with success status and message
    """
    result = settings_collection.delete_one({'page_title': page_title})
    
    if result.deleted_count > 0:
        return {
            'success': True,
            'message': f"Project '{page_title}' deleted successfully"
        }
    else:
        return {
            'success': False,
            'message': f"Project '{page_title}' not found",
            'error': 'not_found'
        } 