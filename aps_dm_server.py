from typing import Any, Dict, List, Optional
import os
import time
import re
from dotenv import load_dotenv
from aps_toolkit import Auth, BIM360
from mcp.server.fastmcp import FastMCP

# region Load environment variables
# Load environment variables
load_dotenv()
APS_CLIENT_ID = os.getenv('APS_CLIENT_ID')
APS_CLIENT_SECRET = os.getenv('APS_CLIENT_SECRET')
APS_REDIRECT_URI = os.getenv('APS_REDIRECT_URI', "http://localhost:8080/api/auth/callback")
APS_SCOPES = os.getenv('APS_SCOPES', 'data:read viewables:read account:read')
APS_TOKEN = os.getenv('APS_TOKEN')  # Direct token if provided

# Cache for the token
TOKEN_CACHE = {
    "token": None,
    "expires_at": 0
}

# endregion

# region masking system
class IDMasker:
    def __init__(self):
        # Maps for each type of ID
        self.hub_map = {}  # Real hub ID -> Masked ID
        self.project_map = {}  # Real project ID -> Masked ID
        self.item_map = {}  # Real item ID -> Masked ID
        self.folder_map = {}  # Real folder ID -> Masked ID
        self.version_map = {}  # Real version ID/URN -> Masked ID
        
        # Reverse maps for lookups
        self.rev_hub_map = {}  # Masked ID -> Real hub ID
        self.rev_project_map = {}  # Masked ID -> Real project ID
        self.rev_item_map = {}  # Masked ID -> Real item ID
        self.rev_folder_map = {}  # Masked ID -> Real folder ID
        self.rev_version_map = {}  # Masked ID -> Real version ID/URN
        
        # Track project-hub relationships
        self.project_to_hub = {}  # Real project ID -> Real hub ID
    
    def register_project_hub(self, project_id: str, hub_id: str):
        """Register which hub a project belongs to."""
        self.project_to_hub[project_id] = hub_id
    
    def get_hub_for_project(self, project_id: str) -> str:
        """Get the hub ID for a project."""
        return self.project_to_hub.get(project_id, None)
    
    def mask_hub_id(self, real_id: str) -> str:
        """Convert a real hub ID to a masked ID."""
        if not real_id:
            return "Unknown"
        if real_id not in self.hub_map:
            masked = f"hub_{len(self.hub_map) + 1}"
            self.hub_map[real_id] = masked
            self.rev_hub_map[masked] = real_id
        return self.hub_map[real_id]
    
    def unmask_hub_id(self, masked_id: str) -> str:
        """Convert a masked hub ID back to the real ID."""
        return self.rev_hub_map.get(masked_id, masked_id)
    
    def mask_project_id(self, real_id: str) -> str:
        """Convert a real project ID to a masked ID."""
        if not real_id:
            return "Unknown"
        if real_id not in self.project_map:
            masked = f"project_{len(self.project_map) + 1}"
            self.project_map[real_id] = masked
            self.rev_project_map[masked] = real_id
        return self.project_map[real_id]
    
    def unmask_project_id(self, masked_id: str) -> str:
        """Convert a masked project ID back to the real ID."""
        return self.rev_project_map.get(masked_id, masked_id)
    
    def mask_folder_id(self, real_id: str) -> str:
        """Convert a real folder ID to a masked ID."""
        if not real_id:
            return "Unknown"
        if real_id not in self.folder_map:
            masked = f"folder_{len(self.folder_map) + 1}"
            self.folder_map[real_id] = masked
            self.rev_folder_map[masked] = real_id
        return self.folder_map[real_id]
    
    def unmask_folder_id(self, masked_id: str) -> str:
        """Convert a masked folder ID back to the real ID."""
        return self.rev_folder_map.get(masked_id, masked_id)
    
    def mask_item_id(self, real_id: str) -> str:
        """Convert a real item ID to a masked ID."""
        if not real_id:
            return "Unknown"
        if real_id not in self.item_map:
            masked = f"item_{len(self.item_map) + 1}"
            self.item_map[real_id] = masked
            self.rev_item_map[masked] = real_id
        return self.item_map[real_id]
    
    def unmask_item_id(self, masked_id: str) -> str:
        """Convert a masked item ID back to the real ID."""
        return self.rev_item_map.get(masked_id, masked_id)
    
    def mask_version(self, real_id: str) -> str:
        """Convert a real version ID/URN to a masked ID."""
        if not real_id:
            return "Unknown"
        if real_id not in self.version_map:
            masked = f"version_{len(self.version_map) + 1}"
            self.version_map[real_id] = masked
            self.rev_version_map[masked] = real_id
        return self.version_map[real_id]
    
    def unmask_version(self, masked_id: str) -> str:
        """Convert a masked version ID/URN back to the real ID."""
        return self.rev_version_map.get(masked_id, masked_id)
    
    def is_masked_id(self, id_str: str) -> bool:
        """Check if an ID is already a masked ID."""
        return bool(re.match(r'^(hub|project|folder|item|version)_\d+$', id_str))

# Create global masker instance
id_masker = IDMasker()
# endregion

# Helper functions
def authenticate() -> str:
    """Authenticate with Autodesk and get access token."""
    # If we have a cached token that hasn't expired, use it
    current_time = time.time()
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expires_at"] > current_time:
        return TOKEN_CACHE["token"]
    
    # If direct token is provided in environment, use it
    if APS_TOKEN:
        TOKEN_CACHE["token"] = APS_TOKEN
        # Set expiration to a reasonable time (1 hour)
        TOKEN_CACHE["expires_at"] = current_time + 3600
        return APS_TOKEN
        
    # Otherwise use 3-legged OAuth
    auth = Auth(APS_CLIENT_ID, APS_CLIENT_SECRET)
    token = auth.auth3leg(APS_REDIRECT_URI, APS_SCOPES)
    
    # Cache the token with an expiration time (1 hour)
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = current_time + 3600
    
    return token

def format_hub(hub: Dict) -> str:
    """Format a hub into a readable string with masked ID."""
    real_id = hub.get('id', 'Unknown')
    masked_id = id_masker.mask_hub_id(real_id)
    
    return f"""
ID: {masked_id}
Name: {hub.get('attributes', {}).get('name', 'Unknown')}
Type: {hub.get('attributes', {}).get('extension', {}).get('type', 'Unknown')}
Region: {hub.get('attributes', {}).get('region', 'Unknown')}
"""

def format_project(project: Dict) -> str:
    """Format a project into a readable string with masked ID."""
    real_id = project.get('id', 'Unknown')
    masked_id = id_masker.mask_project_id(real_id)
    
    return f"""
ID: {masked_id}
Name: {project.get('attributes', {}).get('name', 'Unknown')}
Status: {project.get('attributes', {}).get('status', 'Unknown')}
"""

def format_item(item: Dict) -> str:
    """Format a file/folder item into a readable string with masked ID."""
    attributes = item.get('attributes', {})
    real_id = item.get('id', 'Unknown')
    
    # Mask ID based on item type
    if item.get('type') == 'folders':
        masked_id = id_masker.mask_folder_id(real_id)
    else:
        masked_id = id_masker.mask_item_id(real_id)
    
    return f"""
ID: {masked_id}
Type: {item.get('type', 'Unknown')}
Name: {attributes.get('displayName', 'Unknown')}
File Type: {attributes.get('fileType', 'N/A')}
Last Modified: {attributes.get('lastModifiedTime', 'Unknown')}
"""

# Initialize FastMCP server
mcp = FastMCP("acc")

# Tool implementation
@mcp.tool()
async def get_hubs() -> str:
    """Get all available hubs the user has access to."""
    token = authenticate()
    bim360 = BIM360(token)
    
    data = bim360.get_hubs()
    
    if not data or "data" not in data: 
        return "Unable to fetch hubs or no hubs found."
    
    if not data["data"]:
        return "No hubs found for this account."
    
    hubs = [format_hub(hub) for hub in data["data"]]
    return "\n---\n".join(hubs)

@mcp.tool()
async def get_projects(hub_id: str) -> str:
    """Get all projects within a specified hub.
    
    Args:
        hub_id: The ID or masked ID of the hub to get projects from
    """
    token = authenticate()
    bim360 = BIM360(token)
    
    # Check if we need to unmask the hub ID
    if id_masker.is_masked_id(hub_id):
        real_hub_id = id_masker.unmask_hub_id(hub_id)
    else:
        real_hub_id = hub_id
    
    data = bim360.get_projects(real_hub_id)
    
    if not data or "data" not in data:
        return "Unable to fetch projects or no projects found."
    
    if not data["data"]:
        return "No projects found for this hub."
    
    # Register hub-project relationships
    for project in data["data"]:
        id_masker.register_project_hub(project.get('id'), real_hub_id)
    
    projects = [format_project(project) for project in data["data"]]
    return "\n---\n".join(projects)

@mcp.tool()
async def get_project_files(project_id: str, folder_id: Optional[str] = None, file_type: Optional[str] = None) -> str:
    """Get all files in a project recursively.
    
    Args:
        project_id: The ID or masked ID of the project
        folder_id: Optional folder ID or masked ID to start from (if not provided, finds "Project Files" folder)
        file_type: Optional filter for file type (e.g., "rvt" for Revit files)
    """
    token = authenticate()
    bim360 = BIM360(token)
    
    # Check if we need to unmask the project ID
    if id_masker.is_masked_id(project_id):
        real_project_id = id_masker.unmask_project_id(project_id)
    else:
        real_project_id = project_id
    
    # Get the hub ID for this project
    hub_id = id_masker.get_hub_for_project(real_project_id)
    if not hub_id:
        return f"Cannot find hub ID for project {project_id}. Please use get_projects first to establish the relationship."
    
    # Check if we need to unmask the folder ID
    real_folder_id = None
    if folder_id and folder_id.strip():
        if id_masker.is_masked_id(folder_id):
            real_folder_id = id_masker.unmask_folder_id(folder_id)
        else:
            real_folder_id = folder_id
    
    # Store all items found
    all_items = []
    
    # Recursive function to process folders
    def process_folder(folder_id, folder_name=""):
        # Get folder contents
        contents = bim360.get_folder_contents(real_project_id, folder_id)
        
        if not contents or "data" not in contents:
            return
        
        for item in contents.get("data", []):
            # If it's a folder, process it recursively
            if item.get("type") == "folders":
                folder_attributes = item.get("attributes", {})
                sub_folder_name = folder_attributes.get("displayName", "Unknown Folder")
                sub_folder_id = item.get("id")
                
                # Register the folder ID mapping
                id_masker.mask_folder_id(sub_folder_id)
                
                # Process the subfolder recursively
                process_folder(sub_folder_id, sub_folder_name)
            
            # If it's a file, check if it matches the filter
            elif item.get("type") == "items":
                item_attributes = item.get("attributes", {})
                item_type = item_attributes.get("fileType", "").lower()
                
                # Register the item ID mapping
                item_id = item.get("id")
                id_masker.mask_item_id(item_id)
                
                # If no file_type filter or it matches, add it to our results
                if not file_type or (item_type and file_type.lower() in item_type):
                    all_items.append(item)
    
    try:
        # If a specific folder ID was provided, use it directly
        if real_folder_id:
            process_folder(real_folder_id)
            
        # Otherwise, find the "Project Files" folder
        else:
            # Get top folders
            top_folders = bim360.get_top_folders(hub_id, real_project_id)
            
            if not top_folders or "data" not in top_folders or not top_folders.get("data"):
                return "No top folders found in this project."
            
            # Look for "Project Files" folder
            project_files_folder_id = None
            for folder in top_folders.get("data", []):
                folder_name = folder.get("attributes", {}).get("displayName", "")
                folder_id = folder.get("id")
                
                # Register folder ID mapping
                id_masker.mask_folder_id(folder_id)
                
                # Check if this is the "Project Files" folder
                if folder_name == "Project Files":
                    project_files_folder_id = folder_id
                    break
            
            # If "Project Files" folder was found, process it
            if project_files_folder_id:
                process_folder(project_files_folder_id, "Project Files")
            else:
                # If no "Project Files" folder, just process all top folders
                for folder in top_folders.get("data", []):
                    folder_name = folder.get("attributes", {}).get("displayName", "")
                    folder_id = folder.get("id")
                    process_folder(folder_id, folder_name)
        
        # Return the results
        if not all_items:
            filter_msg = f" matching type '{file_type}'" if file_type else ""
            return f"No files{filter_msg} found in the project."
        
        items_formatted = [format_item(item) for item in all_items]
        return f"Found {len(all_items)} files:\n\n" + "\n---\n".join(items_formatted)
    
    except Exception as e:
        return f"Error accessing project or folder: {str(e)}"

@mcp.tool()
async def get_versions(project_id: str, item_id: str) -> str:
    """Get version information for a specific item.
    
    Args:
        project_id: The ID or masked ID of the project
        item_id: The ID or masked ID of the item to get versions for
    """
    token = authenticate()
    bim360 = BIM360(token)
    
    # Check if we need to unmask the project ID
    if id_masker.is_masked_id(project_id):
        real_project_id = id_masker.unmask_project_id(project_id)
    else:
        real_project_id = project_id
    
    # Check if we need to unmask the item ID
    if id_masker.is_masked_id(item_id):
        real_item_id = id_masker.unmask_item_id(item_id)
    else:
        real_item_id = item_id
        
    try:
        # Get all versions directly using get_item_versions
        versions_data = bim360.get_item_versions(real_project_id, real_item_id)
        
        if not versions_data or "data" not in versions_data or not versions_data["data"]:
            return "No versions available for this item."
        
        # Try to get item name if available in the response
        item_name = "Item"
        if versions_data["data"] and versions_data["data"][0].get("attributes", {}).get("displayName"):
            item_name = versions_data["data"][0].get("attributes", {}).get("displayName")
        
        # Format version information
        version_list = []
        for version in versions_data["data"]:
            attributes = version.get("attributes", {})
            version_id = version.get("id", "Unknown")
            version_num = attributes.get("versionNumber", "Unknown")
            
            # Get basic file information
            file_name = attributes.get("displayName", "Unknown")
            file_type = attributes.get("fileType", "Unknown")
            
            # Get storage size (in bytes) - using storageSize instead of fileSize
            storage_size = attributes.get("storageSize", "Unknown")
            storage_size_formatted = "Unknown size"
            if isinstance(storage_size, (int, float)) and storage_size > 0:
                # Convert to MB with 2 decimal places
                storage_size_formatted = f"{storage_size / (1024*1024):.2f} MB"
            
            # Get creation and modification times
            created_date = attributes.get("createTime", "Unknown")
            modified_date = attributes.get("lastModifiedTime", "Unknown")
            
            # Get Revit-specific information (safe extraction)
            extension_data = version.get("attributes", {}).get("extension", {}).get("data", {})
            revit_version = extension_data.get("revitProjectVersion", "Unknown")
            model_version = extension_data.get("modelVersion", "Unknown")
            publish_type = extension_data.get("publishType", "Unknown")
            process_state = extension_data.get("processState", "Unknown")
            
            # Format the version details
            version_info = f"Version {version_num} (ID: {id_masker.mask_version(version_id)})"
            version_info += f"\nFile: {file_name}"
            version_info += f"\nType: {file_type}"
            version_info += f"\nSize: {storage_size_formatted}"
            
            # Add dates
            if created_date != "Unknown":
                version_info += f"\nCreated: {created_date}"
            if modified_date != "Unknown" and modified_date != created_date:
                version_info += f"\nModified: {modified_date}"
            
            # Add Revit-specific details when available
            if revit_version != "Unknown":
                version_info += f"\nRevit Version: {revit_version}"
            if model_version != "Unknown":
                version_info += f"\nModel Version: {model_version}" # Internal versioning of the Revit model
            if publish_type != "Unknown":
                version_info += f"\nPublish Type: {publish_type}"
            
            version_list.append(version_info)
        
        result = f"Found {len(version_list)} versions for {item_name}:\n\n"
        result += "\n---\n".join(version_list)
        return result
        
    except Exception as e:
        return f"Error getting versions: {str(e)}"

if __name__ == "__main__":
    # Initialize and run the server
    print(f"Starting APS MCP Server")
    mcp.run(transport='stdio')
 