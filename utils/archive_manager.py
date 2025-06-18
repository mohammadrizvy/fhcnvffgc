from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging
from .enhanced_db import EnhancedDatabaseManager
from .config import COLLECTIONS
import os
import json
import shutil

logger = logging.getLogger('discord')

class TicketArchiveManager:
    def __init__(self):
        self.db = EnhancedDatabaseManager()
        
    async def archive_ticket(self, ticket_number: str) -> bool:
        """Archive a closed ticket with all related data"""
        try:
            # Get all ticket related data
            ticket = await self.db.get_ticket(ticket_number)
            if not ticket:
                logger.error(f"No ticket found for archiving: {ticket_number}")
                return False

            messages = await self.db.get_ticket_messages(ticket_number)
            feedback = await self.db.get_feedback(ticket_number)
            
            # Create comprehensive archive record
            archive_data = {
                "ticket_number": ticket_number,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "ticket_data": {
                    # Basic ticket info
                    "user_id": ticket["user_id"],
                    "category": ticket["category"],
                    "status": "archived",
                    "created_at": ticket["created_at"],
                    "closed_at": ticket["closed_at"],
                    "channel_id": ticket["channel_id"],
                    
                    # Service details
                    "service_details": {
                        "boss_type": ticket.get("boss_type"),
                        "tier": ticket.get("tier"),
                        "floor": ticket.get("floor"),
                        "completion_type": ticket.get("completion_type"),
                        "number_of_runs": ticket.get("number_of_runs")
                    },
                    
                    # Staff interaction
                    "staff_interaction": {
                        "claimed_by": ticket.get("claimed_by"),
                        "claim_time": ticket.get("claim_time"),
                        "closed_by": ticket.get("closed_by"),
                        "priority_level": ticket.get("priority_level"),
                        "call_staff_used": ticket.get("call_staff_used", False),
                        "call_staff_timestamp": ticket.get("call_staff_timestamp")
                    }
                },
                
                # Message history
                "messages": [{
                    "content": msg["content"],
                    "author_id": msg["author_id"],
                    "author_name": msg["author_name"],
                    "timestamp": msg["timestamp"],
                    "attachments": msg.get("attachments", [])
                } for msg in messages],
                
                # Feedback data
                "feedback": feedback if feedback else None,
                
                # Statistics
                "statistics": {
                    "total_messages": len(messages),
                    "response_time_minutes": ticket.get("first_staff_response_time"),
                    "resolution_time_hours": ticket.get("resolution_time"),
                    "staff_messages": sum(1 for msg in messages if msg.get("is_staff", False))
                }
            }

            # Store in archive collection
            result = await self.db.db[COLLECTIONS.get('archives', 'ticket_archives')].insert_one(archive_data)
            
            if result.inserted_id:
                # Add to analytics for reporting
                await self._update_archive_analytics(archive_data)
                logger.info(f"Successfully archived ticket {ticket_number}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error archiving ticket {ticket_number}: {e}")
            return False

    async def get_archived_ticket(self, ticket_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve an archived ticket"""
        try:
            return await self.db.db[COLLECTIONS.get('archives', 'ticket_archives')].find_one(
                {"ticket_number": ticket_number}
            )
        except Exception as e:
            logger.error(f"Error retrieving archived ticket {ticket_number}: {e}")
            return None

    async def _update_archive_analytics(self, archive_data: Dict[str, Any]) -> None:
        """Update analytics for archived tickets"""
        try:
            category = archive_data["ticket_data"]["category"]
            resolution_time = archive_data["statistics"]["resolution_time_hours"]
            
            analytics_update = {
                "$inc": {
                    "total_tickets": 1,
                    f"categories.{category}.count": 1,
                    "total_messages": archive_data["statistics"]["total_messages"]
                },
                "$push": {
                    "resolution_times": resolution_time,
                    f"categories.{category}.resolution_times": resolution_time
                }
            }
            
            await self.db.db[COLLECTIONS.get('analytics', 'ticket_analytics')].update_one(
                {"_id": "archive_stats"},
                analytics_update,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating archive analytics: {e}")

    async def get_archive_statistics(self) -> Dict[str, Any]:
        """Get statistics about archived tickets"""
        try:
            stats = await self.db.db[COLLECTIONS.get('analytics', 'ticket_analytics')].find_one(
                {"_id": "archive_stats"}
            )
            
            if not stats:
                return {"total_tickets": 0, "categories": {}}
            
            # Calculate averages for resolution times
            if "resolution_times" in stats:
                stats["average_resolution_time"] = sum(stats["resolution_times"]) / len(stats["resolution_times"])
                
            for category in stats.get("categories", {}).values():
                if "resolution_times" in category:
                    category["average_resolution_time"] = sum(category["resolution_times"]) / len(category["resolution_times"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting archive statistics: {e}")
            return {}

class ArchiveManager:
    def __init__(self, archive_dir='archives'):
        self.archive_dir = archive_dir
        os.makedirs(archive_dir, exist_ok=True)

    def archive_ticket(self, ticket_data, transcript_data=None):
        try:
            ticket_number = ticket_data.get('ticket_number')
            archive_path = os.path.join(self.archive_dir, f'ticket-{ticket_number}')
            os.makedirs(archive_path, exist_ok=True)

            with open(os.path.join(archive_path, 'ticket_data.json'), 'w') as f:
                json.dump(ticket_data, f, indent=4)

            if transcript_data:
                with open(os.path.join(archive_path, 'transcript.json'), 'w') as f:
                    json.dump(transcript_data, f, indent=4)

            return True
        except Exception as e:
            logger.error(f"Error archiving ticket: {e}")
            return False

    def get_archive(self, ticket_number):
        try:
            archive_path = os.path.join(self.archive_dir, f'ticket-{ticket_number}')
            if not os.path.exists(archive_path):
                return None

            ticket_data = {}
            transcript_data = None

            ticket_data_path = os.path.join(archive_path, 'ticket_data.json')
            if os.path.exists(ticket_data_path):
                with open(ticket_data_path, 'r') as f:
                    ticket_data = json.load(f)

            transcript_path = os.path.join(archive_path, 'transcript.json')
            if os.path.exists(transcript_path):
                with open(transcript_path, 'r') as f:
                    transcript_data = json.load(f)

            return {
                'ticket_data': ticket_data,
                'transcript_data': transcript_data
            }
        except Exception as e:
            logger.error(f"Error retrieving archive: {e}")
            return None

    def list_archives(self):
        try:
            archives = []
            for item in os.listdir(self.archive_dir):
                if item.startswith('ticket-'):
                    ticket_number = item.split('-')[1]
                    archive_path = os.path.join(self.archive_dir, item)
                    if os.path.isdir(archive_path):
                        archives.append({
                            'ticket_number': ticket_number,
                            'created_at': datetime.fromtimestamp(os.path.getctime(archive_path)).isoformat(),
                            'size': self._get_archive_size(archive_path)
                        })
            return archives
        except Exception as e:
            logger.error(f"Error listing archives: {e}")
            return []

    def delete_archive(self, ticket_number):
        try:
            archive_path = os.path.join(self.archive_dir, f'ticket-{ticket_number}')
            if os.path.exists(archive_path):
                shutil.rmtree(archive_path)
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting archive: {e}")
            return False

    def _get_archive_size(self, archive_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(archive_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size
