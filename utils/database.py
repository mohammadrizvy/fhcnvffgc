from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import logging
import motor.motor_asyncio
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('discord')

# Database configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DATABASE_NAME = os.getenv('MONGODB_DB_NAME', 'ticket_bot')
COLLECTIONS = {
    'tickets': 'tickets',
    'ticket_messages': 'ticket_messages',
    'feedback': 'feedback',
    'staff_roles': 'staff_roles',
    'user_tickets': 'user_tickets',
    'ticket_logs': 'ticket_logs',
    'bot_config': 'bot_config'
}

class DatabaseManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not DatabaseManager._initialized:
            try:
                # Initialize async client with proper configuration
                self.client = motor.motor_asyncio.AsyncIOMotorClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=10000
                )
                self.db = self.client[DATABASE_NAME]
                
                # Initialize collections
                self.tickets = self.db[COLLECTIONS['tickets']]
                self.ticket_messages = self.db[COLLECTIONS['ticket_messages']]
                self.feedback = self.db[COLLECTIONS['feedback']]
                self.staff_roles = self.db[COLLECTIONS['staff_roles']]
                self.user_tickets = self.db[COLLECTIONS['user_tickets']]
                self.ticket_logs = self.db[COLLECTIONS['ticket_logs']]
                self.bot_config = self.db[COLLECTIONS['bot_config']]
                
                DatabaseManager._initialized = True
                logger.info("Database manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize database manager: {e}")
                raise
    
    async def connect(self):
        """Establish database connection and create indexes"""
        try:
            # Test connection
            await self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            
            # Create indexes
            await self._create_indexes()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False

    async def _create_indexes(self):
        """Create necessary indexes for performance"""
        try:
            # Tickets collection indexes
            await self.tickets.create_index([("user_id", ASCENDING)])
            await self.tickets.create_index([("status", ASCENDING)])
            await self.tickets.create_index([("created_at", DESCENDING)])
            await self.tickets.create_index([("ticket_number", ASCENDING)], unique=True)
            
            # Messages collection indexes
            await self.ticket_messages.create_index([("ticket_number", ASCENDING)])
            await self.ticket_messages.create_index([("timestamp", ASCENDING)])
            
            # User tickets collection indexes
            await self.user_tickets.create_index([("user_id", ASCENDING)], unique=True)
            
            # Feedback collection indexes
            await self.feedback.create_index([("ticket_number", ASCENDING)], unique=True)
            
            # Ticket logs collection indexes
            await self.ticket_logs.create_index([("ticket_number", ASCENDING)])
            await self.ticket_logs.create_index([("timestamp", DESCENDING)])
            
            logger.info("Database indexes created successfully")
        except PyMongoError as e:
            logger.error(f"Error creating database indexes: {e}")
            raise

    async def create_ticket(self, ticket_data: Dict[str, Any]) -> Optional[str]:
        """Create a new ticket in the database"""
        try:
            # Ensure ticket number is unique
            ticket_number = await self.get_next_ticket_number()
            ticket_data['ticket_number'] = ticket_number
            ticket_data['created_at'] = datetime.now(timezone.utc).isoformat()
            ticket_data['status'] = 'open'
            
            result = await self.tickets.insert_one(ticket_data)
            if result.inserted_id:
                # Log ticket creation
                await self.log_ticket_action(
                    ticket_number,
                    'created',
                    ticket_data.get('user_id', 'system')
                )
                return ticket_number
            return None
        except PyMongoError as e:
            logger.error(f"Error creating ticket: {e}")
            return None

    async def get_next_ticket_number(self) -> str:
        """Get the next available ticket number"""
        try:
            last_ticket = await self.tickets.find_one(
                sort=[("ticket_number", DESCENDING)]
            )
            return str((int(last_ticket['ticket_number']) if last_ticket else 0) + 1)
        except Exception as e:
            logger.error(f"Error getting next ticket number: {e}")
            raise

    async def has_open_ticket(self, user_id: str) -> bool:
        """Check if a user has any open tickets"""
        try:
            count = await self.tickets.count_documents({
                "user_id": user_id,
                "status": "open"
            })
            return count > 0
        except PyMongoError as e:
            logger.error(f"Error checking open tickets: {e}")
            return False

    async def get_ticket(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Get ticket by number"""
        try:
            return await self.tickets.find_one({"ticket_number": ticket_number})
        except PyMongoError as e:
            logger.error(f"Error getting ticket: {e}")
            return None

    async def update_ticket(self, ticket_number: str, update_data: Dict[str, Any]) -> bool:
        """Update ticket data"""
        try:
            result = await self.tickets.update_one(
                {"ticket_number": ticket_number},
                {"$set": update_data}
            )
            if result.modified_count > 0:
                # Log ticket update
                await self.log_ticket_action(
                    ticket_number,
                    'updated',
                    update_data.get('updated_by', 'system')
                )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating ticket: {e}")
            return False

    async def store_message(self, message_data: Dict[str, Any]) -> bool:
        """Store a ticket message"""
        try:
            message_data['timestamp'] = datetime.now(timezone.utc).isoformat()
            result = await self.ticket_messages.insert_one(message_data)
            return bool(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Error storing message: {e}")
            return False

    async def get_ticket_messages(self, ticket_number: str) -> List[Dict[str, Any]]:
        """Get all messages for a ticket"""
        try:
            cursor = self.ticket_messages.find(
                {"ticket_number": ticket_number}
            ).sort("timestamp", ASCENDING)
            return await cursor.to_list(length=None)
        except PyMongoError as e:
            logger.error(f"Error getting ticket messages: {e}")
            return []

    async def store_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """Store ticket feedback"""
        try:
            feedback_data['timestamp'] = datetime.now(timezone.utc).isoformat()
            result = await self.feedback.insert_one(feedback_data)
            return bool(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Error storing feedback: {e}")
            return False

    async def get_feedback(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Get feedback for a ticket"""
        try:
            return await self.feedback.find_one({"ticket_number": ticket_number})
        except PyMongoError as e:
            logger.error(f"Error getting feedback: {e}")
            return None

    async def close_ticket(self, ticket_number: str, closed_by: str) -> bool:
        """Close a ticket"""
        try:
            result = await self.tickets.update_one(
                {"ticket_number": ticket_number},
                {
                    "$set": {
                        "status": "closed",
                        "closed_at": datetime.now(timezone.utc).isoformat(),
                        "closed_by": closed_by
                    }
                }
            )
            if result.modified_count > 0:
                await self.log_ticket_action(ticket_number, 'closed', closed_by)
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error closing ticket: {e}")
            return False

    async def cleanup_old_tickets(self, max_age_days: int = 30) -> int:
        """Clean up old tickets"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            result = await self.tickets.delete_many({
                "status": "closed",
                "closed_at": {"$lt": cutoff_date.isoformat()}
            })
            return result.deleted_count
        except PyMongoError as e:
            logger.error(f"Error cleaning up tickets: {e}")
            return 0

    async def get_all_open_tickets(self) -> List[Dict[str, Any]]:
        """Get all open tickets"""
        try:
            cursor = self.tickets.find({"status": "open"})
            return await cursor.to_list(length=None)
        except PyMongoError as e:
            logger.error(f"Error getting open tickets: {e}")
            return []

    async def log_ticket_action(self, ticket_number: str, action: str, user: str) -> bool:
        """Log a ticket action"""
        try:
            log_entry = {
                "ticket_number": ticket_number,
                "action": action,
                "user": user,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            result = await self.ticket_logs.insert_one(log_entry)
            return bool(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Error logging ticket action: {e}")
            return False

    async def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ticket logs"""
        try:
            cursor = self.ticket_logs.find().sort("timestamp", DESCENDING).limit(limit)
            return await cursor.to_list(length=None)
        except PyMongoError as e:
            logger.error(f"Error getting recent logs: {e}")
            return []

    async def close(self):
        """Close database connection"""
        try:
            self.client.close()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")