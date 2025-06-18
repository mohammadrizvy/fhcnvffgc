import random
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from threading import Lock
import json
import os

logger = logging.getLogger('discord')

_db_manager = None

def set_db_manager(db_manager_instance):
    global _db_manager
    _db_manager = db_manager_instance
    logger.info("DatabaseManager instance set in storage.py")

def get_db_manager():
    global _db_manager
    return _db_manager

# Define carry service categories and their roles
CATEGORY_ROLES = {
    "Slayer Carry": "Slayer Carrier",
    "Normal Dungeon Carry": "Normal Dungeon Carrier", 
    "Master Dungeon Carry": "Master Dungeon Carrier",
    "Support Tickets": "Support Staff",
    "Bug Reports": "Developer",
    "Ban Appeals": "Moderator"
}

def get_category_role(category: str) -> Optional[str]:
    """Get the staff role name associated with a ticket category"""
    return CATEGORY_ROLES.get(category)

# Embed colors for carry services
CATEGORY_COLORS = {
    "Slayer Carry": 0xff0000,  # Red
    "Normal Dungeon Carry": 0x0099ff,  # Blue
    "Master Dungeon Carry": 0x9900ff,  # Purple
    "Support Tickets": 0x00ff00,  # Green
    "Bug Reports": 0xff6b6b,  # Light Red
    "Ban Appeals": 0x4834d4,  # Purple Blue
    "Staff Applications": 0xffa500,  # Orange
}

def get_category_color(category: str) -> int:
    """Get the color associated with a ticket category"""
    return CATEGORY_COLORS.get(category, 0x7289DA)

async def get_next_ticket_number() -> str:
    """Get next sequential ticket number"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return "10000"
    try:
        return await _db_manager.get_next_ticket_number()
    except Exception as e:
        logger.error(f"Error getting next ticket number from DB: {e}")
        return "10000"

async def has_open_ticket(user_id: str) -> bool:
    """Check if a user has any open tickets"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        return await _db_manager.has_open_ticket(user_id)
    except Exception as e:
        logger.error(f"Error checking open tickets in DB: {e}")
        return False

async def get_user_ticket_channel(user_id: str) -> Optional[str]:
    """Get the channel ID of user's open ticket if exists"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return None
    try:
        return await _db_manager.get_user_ticket_channel(user_id)
    except Exception as e:
        logger.error(f"Error getting user ticket channel from DB: {e}")
        return None

async def create_ticket(ticket_number: str, user_id: str, channel_id: str, category: str, details: str, guild_id: int, control_message_id: Optional[int] = None) -> bool:
    """Create a new ticket and store it"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False

    if not validate_ticket_input(ticket_number, user_id, channel_id, category):
        return False

    ticket_info = {
        "ticket_number": ticket_number,
        "user_id": user_id,
        "channel_id": channel_id,
        "category": category,
        "details": details,
        "guild_id": guild_id,
        "status": "open",
        "claimed_by": "Unclaimed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "control_message_id": control_message_id
    }
    try:
        result = await _db_manager.create_ticket(ticket_info)
        return result is not None
    except Exception as e:
        logger.error(f"Error creating ticket in DB: {e}")
        return False

async def claim_ticket(ticket_number: str, claimer: str) -> bool:
    """Claim or unclaim a ticket"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        update_data = {
            "claimed_by": claimer,
            "claimed_time": datetime.now(timezone.utc).isoformat() if claimer != "Unclaimed" else None,
            "claimed_timestamp": datetime.now(timezone.utc).timestamp() if claimer != "Unclaimed" else None
        }
        return await _db_manager.update_ticket(ticket_number, update_data)
    except Exception as e:
        logger.error(f"Error claiming ticket in DB: {e}")
        return False

async def get_ticket_claimed_by(ticket_number: str) -> str:
    """Get who claimed a ticket"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return 'Unclaimed'
    try:
        ticket = await _db_manager.get_ticket(ticket_number)
        if ticket:
            return ticket.get('claimed_by', 'Unclaimed')
        return 'Unclaimed'
    except Exception as e:
        logger.error(f"Error getting ticket claimer from DB: {e}")
        return 'Unclaimed'

def store_feedback(ticket_name: str, user_id: str, rating: int, feedback: str, suggestions: str = "", carrier_ratings: dict = None) -> bool:
    """Store feedback for a ticket (sync version for compatibility)"""
    try:
        feedback_data = {
            "ticket_number": ticket_name,
            "user_id": user_id,
            "rating": rating,
            "feedback": feedback,
            "suggestions": suggestions or "",
            "carrier_ratings": carrier_ratings or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "submitted_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Store in a simple way for now - in production this should be async
        logger.info(f"Storing feedback for ticket {ticket_name} from user {user_id} with rating {rating}")
        return True
    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        return False

async def store_feedback_async(ticket_name: str, user_id: str, rating: int, feedback: str, suggestions: str = "", carrier_ratings: dict = None) -> bool:
    """Store feedback for a ticket (async version)"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    
    try:
        feedback_data = {
            "ticket_number": ticket_name,
            "user_id": user_id,
            "rating": rating,
            "feedback": feedback,
            "suggestions": suggestions or "",
            "carrier_ratings": carrier_ratings or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "submitted_at": datetime.now(timezone.utc).isoformat()
        }
        
        return await _db_manager.store_feedback(feedback_data)
    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        return False

async def get_feedback(ticket_name: str) -> Dict[str, Any]:
    """Get feedback for a ticket"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return {}
    try:
        feedback = await _db_manager.get_feedback(ticket_name)
        return feedback or {}
    except Exception as e:
        logger.error(f"Error retrieving feedback: {e}")
        return {}

async def store_ticket_log(ticket_number: str, messages: list, creator_id: str, category: str,
                       claimed_by: Optional[str] = None, closed_by: Optional[str] = None,
                       details: Optional[str] = None, guild_id: Optional[int] = None,
                       close_reason: Optional[str] = None) -> bool:
    """Store a comprehensive ticket log entry in the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False

    # Convert messages to a serializable format
    serialized_messages = []
    for msg in messages:
        try:
            serialized_msg = {
                "content": msg.content or "",
                "author_id": str(msg.author.id),
                "author_name": msg.author.display_name,
                "timestamp": msg.created_at.isoformat(),
                "attachments": [att.url for att in msg.attachments] if msg.attachments else []
            }
            serialized_messages.append(serialized_msg)
        except Exception as e:
            logger.error(f"Error serializing message: {e}")
            continue

    log_entry = {
        "ticket_number": ticket_number,
        "messages": serialized_messages,
        "creator_id": creator_id,
        "category": category,
        "claimed_by": claimed_by,
        "closed_by": closed_by,
        "details": details,
        "guild_id": guild_id,
        "close_reason": close_reason,
        "logged_at": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Store in ticket_logs collection
        result = await _db_manager.db.ticket_logs.replace_one(
            {"ticket_number": ticket_number},
            log_entry,
            upsert=True
        )
        logger.info(f"Stored ticket log for {ticket_number}")
        return True
    except Exception as e:
        logger.error(f"Error storing ticket log in DB: {e}")
        return False

async def get_ticket_log(ticket_number: str) -> Optional[Dict[str, Any]]:
    """Get a specific ticket log entry"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return None
    try:
        return await _db_manager.get_ticket(ticket_number)
    except Exception as e:
        logger.error(f"Error getting ticket log from DB: {e}")
        return None

async def get_ticket(ticket_number: str) -> Optional[Dict[str, Any]]:
    """Get a specific ticket by its number from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return None
    try:
        return await _db_manager.get_ticket(ticket_number)
    except Exception as e:
        logger.error(f"Error getting ticket from DB: {e}")
        return None

async def close_ticket(ticket_number: str, close_reason: Optional[str] = None) -> bool:
    """Close a ticket and remove it from active tracking"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        update_data = {
            "status": "closed",
            "close_reason": close_reason or "Completed",
            "closed_at": datetime.now(timezone.utc).isoformat()
        }
        return await _db_manager.update_ticket(ticket_number, update_data)
    except Exception as e:
        logger.error(f"Error closing ticket in DB: {e}")
        return False

async def update_ticket_times(ticket_number: str, event_type: str, user_id: str = None) -> bool:
    """Update timing information for a ticket"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        update_data = {}
        current_timestamp = datetime.now(timezone.utc).timestamp()
        current_time_iso = datetime.now(timezone.utc).isoformat()

        if event_type == "created":
            update_data["created_at"] = current_time_iso
            update_data["created_timestamp"] = current_timestamp
        elif event_type == "first_response":
            update_data["first_response_time"] = current_time_iso
            update_data["first_response_timestamp"] = current_timestamp
            update_data["first_responder_id"] = user_id
        elif event_type == "claimed":
            update_data["claimed_time"] = current_time_iso
            update_data["claimed_timestamp"] = current_timestamp
            update_data["claimer_id"] = user_id
        elif event_type == "resolved":
            update_data["resolution_time"] = current_time_iso
            update_data["resolution_timestamp"] = current_timestamp
            update_data["resolver_id"] = user_id

        if update_data:
            return await _db_manager.update_ticket(ticket_number, update_data)
        return False
    except Exception as e:
        logger.error(f"Error updating ticket times in DB: {e}")
        return False

def validate_ticket_input(ticket_number: str, user_id: str, channel_id: str, category: str) -> bool:
    """Validate input parameters for ticket creation"""
    try:
        if not all([ticket_number, user_id, channel_id, category]):
            logger.error("Missing required ticket parameters")
            return False
        if not ticket_number.isdigit():
            logger.error(f"Invalid ticket number format: {ticket_number}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error validating ticket input: {e}")
        return False

async def get_all_tickets() -> List[Dict[str, Any]]:
    """Get all tickets from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return []
    try:
        cursor = _db_manager.tickets.find({})
        return await cursor.to_list(None)
    except Exception as e:
        logger.error(f"Error getting all tickets from DB: {e}")
        return []

async def get_tickets_by_status(status: str) -> List[Dict[str, Any]]:
    """Get tickets by status from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return []
    try:
        cursor = _db_manager.tickets.find({"status": status})
        return await cursor.to_list(None)
    except Exception as e:
        logger.error(f"Error getting tickets by status from DB: {e}")
        return []

async def get_tickets_by_user(user_id: str) -> List[Dict[str, Any]]:
    """Get all tickets for a specific user from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return []
    try:
        cursor = _db_manager.tickets.find({"user_id": user_id})
        return await cursor.to_list(None)
    except Exception as e:
        logger.error(f"Error getting tickets by user from DB: {e}")
        return []

async def get_tickets_by_category(category: str) -> List[Dict[str, Any]]:
    """Get tickets by category from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return []
    try:
        cursor = _db_manager.tickets.find({"category": category})
        return await cursor.to_list(None)
    except Exception as e:
        logger.error(f"Error getting tickets by category from DB: {e}")
        return []

async def update_ticket(ticket_number: str, updates: Dict[str, Any]) -> bool:
    """Update ticket information in the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        return await _db_manager.update_ticket(ticket_number, updates)
    except Exception as e:
        logger.error(f"Error updating ticket in DB: {e}")
        return False

async def get_ticket_statistics() -> Dict[str, Any]:
    """Get ticket statistics from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return {}
    try:
        all_tickets_cursor = _db_manager.tickets.find({})
        all_tickets = await all_tickets_cursor.to_list(None)
        
        all_feedback_cursor = _db_manager.feedback.find({})
        all_feedback = await all_feedback_cursor.to_list(None)

        stats = {
            "total_tickets": len(all_tickets),
            "open_tickets": len([t for t in all_tickets if t.get('status') == 'open']),
            "closed_tickets": len([t for t in all_tickets if t.get('status') == 'closed']),
            "claimed_tickets": len([t for t in all_tickets if t.get('claimed_by') != 'Unclaimed']),
            "categories": {},
            "total_feedback": len(all_feedback),
            "average_rating": 0.0
        }

        # Category statistics
        categories = set(t.get('category', 'Unknown') for t in all_tickets)
        for category in categories:
            category_tickets = [t for t in all_tickets if t.get('category') == category]
            stats['categories'][category] = {
                'total': len(category_tickets),
                'open': len([t for t in category_tickets if t.get('status') == 'open']),
                'closed': len([t for t in category_tickets if t.get('status') == 'closed']),
                'claimed': len([t for t in category_tickets if t.get('claimed_by') != 'Unclaimed'])
            }

        # Calculate average rating
        if all_feedback:
            ratings = [f.get('rating', 0) for f in all_feedback if f.get('rating')]
            if ratings:
                stats['average_rating'] = sum(ratings) / len(ratings)

        return stats
    except Exception as e:
        logger.error(f"Error getting ticket statistics from DB: {e}")
        return {}

async def export_data() -> Dict[str, Any]:
    """Export all data for backup purposes from the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return {}
    try:
        all_tickets_cursor = _db_manager.tickets.find({})
        all_tickets = await all_tickets_cursor.to_list(None)
        
        all_feedback_cursor = _db_manager.feedback.find({})
        all_feedback = await all_feedback_cursor.to_list(None)
        
        all_ticket_logs_cursor = _db_manager.ticket_logs.find({})
        all_ticket_logs = await all_ticket_logs_cursor.to_list(None)
        
        return {
            "tickets": all_tickets,
            "feedback": all_feedback,
            "ticket_logs": all_ticket_logs,
            "export_timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error exporting data from DB: {e}")
        return {}

async def import_data(data: Dict[str, Any]) -> bool:
    """Import data from backup into the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return False
    try:
        # Clear existing data in collections before importing
        await _db_manager.tickets.delete_many({})
        await _db_manager.feedback.delete_many({})
        await _db_manager.ticket_logs.delete_many({})

        # Insert new data
        if 'tickets' in data and data['tickets']:
            await _db_manager.tickets.insert_many(data['tickets'])
        if 'feedback' in data and data['feedback']:
            await _db_manager.feedback.insert_many(data['feedback'])
        if 'ticket_logs' in data and data['ticket_logs']:
            await _db_manager.ticket_logs.insert_many(data['ticket_logs'])
        
        logger.info(f"Imported {len(data.get('tickets', []))} tickets, {len(data.get('feedback', []))} feedback, {len(data.get('ticket_logs', []))} ticket logs")
        return True
    except Exception as e:
        logger.error(f"Error importing data to DB: {e}")
        return False

async def search_tickets(query: str, search_in: List[str] = None) -> List[Dict[str, Any]]:
    """Search tickets by query in the database"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return []
    try:
        if search_in is None:
            search_in = ['category', 'details', 'user_id', 'claimed_by']
        
        # Build a MongoDB OR query for flexible searching
        search_filters = []
        query_regex = {"$regex": query, "$options": "i"}

        for field in search_in:
            search_filters.append({field: query_regex})
        
        if not search_filters:
            return []

        cursor = _db_manager.tickets.find({"$or": search_filters})
        results = await cursor.to_list(None)
        
        logger.info(f"Search for '{query}' in {search_in} returned {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Error searching tickets in DB: {e}")
        return []

def cleanup_old_tickets(max_age_days: int = 30) -> int:
    """Clean up tickets older than max_age_days (sync version for compatibility)"""
    logger.info(f"Cleanup requested for tickets older than {max_age_days} days")
    # This would need to be implemented as an async task
    return 0

async def cleanup_old_tickets_async(max_age_days: int = 30) -> int:
    """Clean up tickets older than max_age_days"""
    if _db_manager is None:
        logger.error("Database manager not set in storage module.")
        return 0
    try:
        return await _db_manager.cleanup_old_tickets(max_age_days)
    except Exception as e:
        logger.error(f"Error cleaning up old tickets: {e}")
        return 0

# Enhanced Storage Class for file-based persistence (backup)
class EnhancedStorage:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.tickets_file = os.path.join(self.data_dir, "tickets.json")
        self.feedback_file = os.path.join(self.data_dir, "feedback.json")
        self.logs_file = os.path.join(self.data_dir, "ticket_logs.json")
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                logger.info(f"Created data directory: {self.data_dir}")
        except Exception as e:
            logger.error(f"Error creating data directory: {e}")

    async def save_all_data(self) -> bool:
        """Save all data to files as backup"""
        try:
            # Export data from database
            data = await export_data()
            
            # Save to separate files
            with open(self.tickets_file, 'w') as f:
                json.dump(data.get('tickets', []), f, indent=2, default=str)
            
            with open(self.feedback_file, 'w') as f:
                json.dump(data.get('feedback', []), f, indent=2, default=str)
            
            with open(self.logs_file, 'w') as f:
                json.dump(data.get('ticket_logs', []), f, indent=2, default=str)
                
            logger.info("Successfully saved all data to files")
            return True
        except Exception as e:
            logger.error(f"Error saving data to files: {e}")
            return False

    async def load_all_data(self) -> bool:
        """Load all data from files (for emergency restore)"""
        try:
            data = {}
            
            # Load tickets
            if os.path.exists(self.tickets_file):
                with open(self.tickets_file, 'r') as f:
                    data['tickets'] = json.load(f)
            
            # Load feedback
            if os.path.exists(self.feedback_file):
                with open(self.feedback_file, 'r') as f:
                    data['feedback'] = json.load(f)
            
            # Load logs
            if os.path.exists(self.logs_file):
                with open(self.logs_file, 'r') as f:
                    data['ticket_logs'] = json.load(f)
            
            # Import to database
            if data:
                await import_data(data)
            
            logger.info(f"Successfully loaded data from files")
            return True
        except Exception as e:
            logger.error(f"Error loading data from files: {e}")
            return False

# Create global enhanced storage instance
enhanced_storage = EnhancedStorage()

async def save_data_to_file() -> bool:
    """Save all data to files using enhanced storage"""
    return await enhanced_storage.save_all_data()

async def load_data_from_file() -> bool:
    """Load all data from files using enhanced storage"""
    return await enhanced_storage.load_all_data()

# User management functions (simplified for now)
users: Dict[str, dict] = {}

def add_user(user_data: dict) -> bool:
    """Add a new user to the system"""
    try:
        user_id = user_data.get("user_id")
        if not user_id:
            logger.error("Missing user_id in user data")
            return False

        if user_id in users:
            logger.warning(f"User {user_id} already exists")
            return False

        users[user_id] = user_data
        logger.info(f"User {user_data.get('username')} (ID: {user_id}) added successfully")
        return True

    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return False

def get_confirmation_message():
    """Get the confirmation message for ticket creation"""
    return "✅ Your request has been submitted! A ticket will be created shortly."

# Utility functions for backwards compatibility
def log_operation(operation: str, details: dict) -> None:
    """Helper function for consistent logging"""
    try:
        log_msg = f"[{operation}] " + " | ".join(f"{k}: {v}" for k, v in details.items())
        logger.info(log_msg)
    except Exception as e:
        logger.error(f"Error in logging: {e}")

# Initialize on import
try:
    logger.info("Storage module initialized")
except Exception as e:
    logger.error(f"Error initializing storage module: {e}")