from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone, timedelta
import logging
import motor.motor_asyncio
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
import asyncio
import json
from redis import asyncio as aioredis
import time
from functools import wraps
import os
from pathlib import Path
import gzip
import aiocron
from .config import MONGODB_URI, DATABASE_NAME, COLLECTIONS, FEEDBACK_CATEGORIES

logger = logging.getLogger('discord')

def measure_time(func):
    """Decorator to measure function execution time"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        
        # Log operation time
        logger.info(f"Operation {func.__name__} took {(end-start)*1000:.2f}ms")
        return result
    return wrapper

class EnhancedDatabaseManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EnhancedDatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not EnhancedDatabaseManager._initialized:
            # MongoDB setup
            if not MONGODB_URI:
                raise ValueError("MongoDB URI not found in environment variables")
            
            # Initialize MongoDB client with connection pooling
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                MONGODB_URI,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=50000
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
            self.transcripts = self.db[COLLECTIONS['transcripts']]
            self.feedback_categories = self.db[COLLECTIONS['feedback_categories']]
            
            # Initialize Redis cache
            self.cache = aioredis.from_url(
                os.getenv('REDIS_URI', 'redis://localhost'),
                encoding='utf-8',
                decode_responses=True
            )
            
            # Set up backup directory
            self.backup_dir = Path('backups')
            self.backup_dir.mkdir(exist_ok=True)
            
            # Initialize metrics
            self.metrics = {
                'operations': 0,
                'cache_hits': 0,
                'cache_misses': 0,
                'avg_response_time': 0
            }
            
            # Set up automatic backups (daily at 3 AM)
            aiocron.crontab('0 3 * * *', func=self.auto_backup)
            
            # Create indexes
            asyncio.create_task(self._create_indexes())
            EnhancedDatabaseManager._initialized = True
    
    async def _create_indexes(self):
        """Create optimized indexes for better query performance"""
        try:
            # Tickets collection indexes
            await self.tickets.create_index([
                ("user_id", ASCENDING),
                ("status", ASCENDING),
                ("created_at", DESCENDING)
            ])
            await self.tickets.create_index([("category", ASCENDING)])
            
            # Messages collection indexes
            await self.ticket_messages.create_index([
                ("ticket_number", ASCENDING),
                ("timestamp", ASCENDING)
            ])
            
            # Compound index for user tickets
            await self.user_tickets.create_index([
                ("user_id", ASCENDING),
                ("current_ticket_number", ASCENDING)
            ], unique=True)
            
            # New indexes for transcripts and feedback
            await self.transcripts.create_index([
                ("ticket_number", ASCENDING),
                ("created_at", DESCENDING)
            ])
            
            await self.feedback_categories.create_index([
                ("category_id", ASCENDING)
            ], unique=True)
            
            logger.info("Enhanced database indexes created successfully")
        except PyMongoError as e:
            logger.error(f"Error creating enhanced database indexes: {e}")

    async def _cache_get(self, key: str) -> Optional[Dict]:
        """Get data from cache"""
        try:
            data = await self.cache.get(key)
            if data:
                self.metrics['cache_hits'] += 1
                return json.loads(data)
            self.metrics['cache_misses'] += 1
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    async def _cache_set(self, key: str, value: Dict, expire: int = 3600):
        """Set data in cache with expiration"""
        try:
            await self.cache.set(
                key,
                json.dumps(value),
                ex=expire
            )
        except Exception as e:
            logger.error(f"Cache set error: {e}")

    @measure_time
    async def get_ticket(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Get ticket with caching"""
        cache_key = f"ticket:{ticket_number}"
        
        # Try cache first
        cached_data = await self._cache_get(cache_key)
        if cached_data:
            return cached_data
            
        # Get from database
        ticket = await self.tickets.find_one({"ticket_number": ticket_number})
        if ticket:
            await self._cache_set(cache_key, ticket)
        return ticket

    @measure_time
    async def create_ticket(self, ticket_data: Dict[str, Any]) -> Optional[str]:
        """Create ticket with automatic caching"""
        try:
            result = await self.tickets.insert_one(ticket_data)
            if result.inserted_id:
                ticket_number = str(ticket_data['ticket_number'])
                # Cache the new ticket
                await self._cache_set(f"ticket:{ticket_number}", ticket_data)
                return ticket_number
            return None
        except PyMongoError as e:
            logger.error(f"Error creating ticket: {e}")
            return None

    async def auto_backup(self):
        """Automatic daily backup"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"backup_{timestamp}.gz"
            
            # Get all collections data
            backup_data = {}
            for collection_name in COLLECTIONS.values():
                cursor = self.db[collection_name].find({})
                backup_data[collection_name] = await cursor.to_list(None)
            
            # Compress and save
            with gzip.open(backup_file, 'wt') as f:
                json.dump(backup_data, f)
            
            # Keep only last 7 backups
            backups = sorted(self.backup_dir.glob('backup_*.gz'))
            for old_backup in backups[:-7]:
                old_backup.unlink()
                
            logger.info(f"Backup created successfully: {backup_file}")
        except Exception as e:
            logger.error(f"Backup error: {e}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get database performance metrics"""
        return {
            **self.metrics,
            'cache_hit_ratio': self.metrics['cache_hits'] / 
                (self.metrics['cache_hits'] + self.metrics['cache_misses']) 
                if (self.metrics['cache_hits'] + self.metrics['cache_misses']) > 0 else 0
        }

    async def restore_backup(self, backup_file: str) -> bool:
        """Restore from backup file"""
        try:
            with gzip.open(backup_file, 'rt') as f:
                backup_data = json.load(f)
            
            # Restore each collection
            for collection_name, data in backup_data.items():
                if data:
                    await self.db[collection_name].delete_many({})
                    await self.db[collection_name].insert_many(data)
            
            return True
        except Exception as e:
            logger.error(f"Restore error: {e}")
            return False

    async def get_ticket_stats(self) -> Dict[str, Any]:
        """Get ticket statistics"""
        try:
            stats = {
                'total_tickets': await self.tickets.count_documents({}),
                'open_tickets': await self.tickets.count_documents({"status": "open"}),
                'closed_tickets': await self.tickets.count_documents({"status": "closed"}),
                'categories': {}
            }
            
            # Get stats per category
            categories = await self.tickets.distinct("category")
            for category in categories:
                stats['categories'][category] = {
                    'total': await self.tickets.count_documents({"category": category}),
                    'open': await self.tickets.count_documents({
                        "category": category,
                        "status": "open"
                    })
                }
            
            return stats
        except PyMongoError as e:
            logger.error(f"Error getting ticket stats: {e}")
            return {}

    @measure_time
    async def close_ticket(self, ticket_number: str) -> bool:
        """Close and archive a ticket"""
        try:
            # First close the ticket
            result = await self.tickets.update_one(
                {"ticket_number": ticket_number},
                {
                    "$set": {
                        "status": "closed",
                        "closed_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                # Archive the ticket
                from .archive_manager import TicketArchiveManager
                archive_manager = TicketArchiveManager()
                await archive_manager.archive_ticket(ticket_number)
                
                # Clear ticket cache
                await self.cache.delete(f"ticket:{ticket_number}")
                
                logger.info(f"Ticket {ticket_number} closed and archived successfully")
                return True
                
            logger.warning(f"Attempted to close non-existent ticket: {ticket_number}")
            return False
            
        except PyMongoError as e:
            logger.error(f"Error closing ticket: {e}")
            return False

    @measure_time
    async def store_transcript(self, ticket_number: str, transcript_data: Dict[str, Any]) -> bool:
        """Store a ticket transcript"""
        try:
            transcript = {
                "ticket_number": ticket_number,
                "created_at": datetime.now(timezone.utc),
                "sections": transcript_data
            }
            result = await self.transcripts.insert_one(transcript)
            return bool(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Error storing transcript: {e}")
            return False

    @measure_time
    async def get_transcript(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Get a ticket transcript"""
        try:
            return await self.transcripts.find_one(
                {"ticket_number": ticket_number},
                sort=[("created_at", DESCENDING)]
            )
        except PyMongoError as e:
            logger.error(f"Error getting transcript: {e}")
            return None

    @measure_time
    async def store_feedback_with_categories(self, feedback_data: Dict[str, Any]) -> bool:
        """Store feedback with category ratings"""
        try:
            feedback = {
                "ticket_number": feedback_data["ticket_number"],
                "user_id": feedback_data["user_id"],
                "overall_rating": feedback_data["overall_rating"],
                "category_ratings": feedback_data["category_ratings"],
                "comments": feedback_data.get("comments", ""),
                "submitted_at": datetime.now(timezone.utc)
            }
            result = await self.feedback.insert_one(feedback)
            return bool(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Error storing feedback with categories: {e}")
            return False

    @measure_time
    async def get_feedback_categories(self) -> Dict[str, Any]:
        """Get all feedback categories"""
        try:
            categories = await self.feedback_categories.find().to_list(None)
            return {cat["category_id"]: cat for cat in categories}
        except PyMongoError as e:
            logger.error(f"Error getting feedback categories: {e}")
            return {}

    @measure_time
    async def initialize_feedback_categories(self) -> bool:
        """Initialize feedback categories from config"""
        try:
            for category_id, category_data in FEEDBACK_CATEGORIES.items():
                await self.feedback_categories.update_one(
                    {"category_id": category_id},
                    {"$set": category_data},
                    upsert=True
                )
            return True
        except PyMongoError as e:
            logger.error(f"Error initializing feedback categories: {e}")
            return False

    @measure_time
    async def get_feedback_stats(self) -> Dict[str, Any]:
        """Get feedback statistics"""
        try:
            stats = {
                "total_feedback": await self.feedback.count_documents({}),
                "average_rating": 0,
                "category_stats": {}
            }
            
            # Calculate average rating
            pipeline = [
                {"$group": {"_id": None, "avg": {"$avg": "$overall_rating"}}}
            ]
            result = await self.feedback.aggregate(pipeline).to_list(1)
            if result:
                stats["average_rating"] = result[0]["avg"]
            
            # Calculate category statistics
            for category_id in FEEDBACK_CATEGORIES:
                pipeline = [
                    {"$unwind": "$category_ratings"},
                    {"$match": {"category_ratings.category": category_id}},
                    {"$group": {
                        "_id": "$category_ratings.rating",
                        "count": {"$sum": 1}
                    }}
                ]
                category_stats = await self.feedback.aggregate(pipeline).to_list(None)
                stats["category_stats"][category_id] = category_stats
            
            return stats
        except PyMongoError as e:
            logger.error(f"Error getting feedback stats: {e}")
            return {}
