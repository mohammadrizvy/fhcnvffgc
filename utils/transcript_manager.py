import discord
import io
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging
import json
import os
import aiofiles
import asyncio

logger = logging.getLogger('discord')

class TranscriptManager:
    def __init__(self, bot):
        self.bot = bot
        self.transcript_dir = "transcripts"
        os.makedirs(self.transcript_dir, exist_ok=True)
        logger.info("Transcript Manager initialized")

    async def generate_transcript_file(self, ticket_number: str, messages: List[discord.Message], 
                                     ticket_data: Dict[str, Any]) -> Optional[str]:
        """Generate text transcript file and return its filepath"""
        try:
            # Format the transcript
            transcript_content = await self._format_transcript(ticket_number, messages, ticket_data)
            
            # Create a unique filename
            filename = f"transcript_{ticket_number}_{uuid.uuid4().hex[:8]}.txt"
            filepath = os.path.join(self.transcript_dir, filename)
            
            # Write content to file
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(transcript_content)
            
            logger.info(f"Generated text transcript: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating transcript file: {e}")
            return None

    async def generate_comprehensive_transcript(self, ticket_number: str, messages: List[discord.Message], 
                                             ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate text transcript only"""
        results = {
            'ticket_number': ticket_number,
            'text_file': None
        }
        
        try:
            # Generate text transcript and get the filepath
            text_filepath = await self.generate_transcript_file(ticket_number, messages, ticket_data)
            if text_filepath:
                results['text_file'] = text_filepath
            
            # Store transcript metadata
            await self.store_transcript_metadata(ticket_number, results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error generating comprehensive transcript: {e}")
            return results

    async def _format_transcript(self, ticket_number: str, messages: List[discord.Message], 
                          ticket_data: Dict[str, Any]) -> str:
        """Format text transcript with improved formatting and accurate creator information"""
        lines = []
        
        # Header with ticket number and branding
        lines.append("=" * 100)
        lines.append(f"{'FakePixel Giveaways Ticket Transcript':^100}")
        lines.append("=" * 100)
        lines.append("")
        
        # Ticket Information Section
        lines.append("📋 TICKET INFORMATION")
        lines.append("-" * 100)
        
        # Get creator information with improved lookup
        creator_id = ticket_data.get('creator_id')
        creator_name = "Unknown"
        creator_roles = []
        
        if creator_id:
            try:
                # First try to get user from cache
                creator = self.bot.get_user(int(creator_id))
                if not creator:
                    # If not in cache, try to fetch user
                    creator = await self.bot.fetch_user(int(creator_id))
                
                if creator:
                    creator_name = str(creator)
                    # Get creator's roles if available
                    if hasattr(creator, 'roles'):
                        creator_roles = [role.name for role in creator.roles if role.name != "@everyone"]
            except (ValueError, discord.NotFound) as e:
                logger.error(f"Error fetching creator info: {e}")
                # Try to get creator from messages if available
                for msg in messages:
                    if str(msg.author.id) == str(creator_id):
                        creator_name = str(msg.author)
                        creator_roles = [role.name for role in msg.author.roles if role.name != "@everyone"]
                        break
        
        # Get claimed by information with improved lookup
        claimed_by_id = ticket_data.get('claimed_by')
        claimed_by_name = "Unclaimed"
        claimed_by_roles = []
        
        if claimed_by_id and claimed_by_id != "Unclaimed":
            try:
                # First try to get user from cache
                claimed_by = self.bot.get_user(int(claimed_by_id))
                if not claimed_by:
                    # If not in cache, try to fetch user
                    claimed_by = await self.bot.fetch_user(int(claimed_by_id))
                
                if claimed_by:
                    claimed_by_name = str(claimed_by)
                    # Get claimed by user's roles if available
                    if hasattr(claimed_by, 'roles'):
                        claimed_by_roles = [role.name for role in claimed_by.roles if role.name != "@everyone"]
            except (ValueError, discord.NotFound) as e:
                logger.error(f"Error fetching claimed by info: {e}")
                # Try to get claimed by from messages if available
                for msg in messages:
                    if str(msg.author.id) == str(claimed_by_id):
                        claimed_by_name = str(msg.author)
                        claimed_by_roles = [role.name for role in msg.author.roles if role.name != "@everyone"]
                        break

        # Add ticket information with improved formatting
        lines.append(f"Ticket Number: #{ticket_number}")
        lines.append(f"Category: {ticket_data.get('category', 'Unknown')}")
        lines.append(f"Created by: {creator_name}")
        lines.append(f"Claimed by: {claimed_by_name}")
        
        # Format timestamps
        created_at = ticket_data.get('created_at', 'Unknown')
        if created_at != 'Unknown':
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                created_at = created_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                pass
        lines.append(f"Created at: {created_at}")
        
        # Calculate duration if possible
        if created_at != 'Unknown' and messages:
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                last_message = messages[-1].created_at
                duration = last_message - created_dt
                days = duration.days
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                seconds = duration.seconds % 60
                duration_str = f"{days}d {hours}h {minutes}m {seconds}s"
                lines.append(f"Duration: {duration_str}")
            except:
                pass
        
        lines.append(f"Total Messages: {len(messages)}")
        lines.append(f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("")
        
        # Conversation Log Section
        lines.append("💬 CONVERSATION LOG")
        lines.append("-" * 100)
        
        # Track participants and their roles
        participants = {}
        
        # Format messages with more detail
        for msg in messages:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            author = msg.author
            author_name = str(author)
            
            # Track participant information
            if author.id not in participants:
                participants[author.id] = {
                    'name': author_name,
                    'roles': [role.name for role in author.roles if role.name != "@everyone"],
                    'message_count': 0
                }
            participants[author.id]['message_count'] += 1
            
            # Format message content with more detail
            content = msg.content or "[embed/attachment]"
            
            # Add attachments information
            if msg.attachments:
                content += "\n" + "\n".join(
                    f"[Attachment: {a.filename} ({self._format_size(a.size)})]"
                    for a in msg.attachments
                )
            
            # Add embeds information
            if msg.embeds:
                for embed in msg.embeds:
                    embed_info = []
                    if embed.title:
                        embed_info.append(f"Title: {embed.title}")
                    if embed.description:
                        embed_info.append(f"Description: {embed.description}")
                    if embed.fields:
                        embed_info.append("Fields:")
                        for field in embed.fields:
                            embed_info.append(f"  - {field.name}: {field.value}")
                    content += "\n" + "\n".join(f"[Embed: {line}]" for line in embed_info)
            
            # Add role indicator for staff
            role_indicator = ""
            if any(role.name in ["Staff", "Admin", "Moderator", "Carrier"] for role in msg.author.roles):
                role_indicator = " [Staff]"
            
            # Add message ID and type
            lines.append(f"[{timestamp}] {author_name}{role_indicator} (ID: {msg.id}):")
            # Indent message content for better readability
            for line in content.split('\n'):
                lines.append(f"    {line}")
            lines.append("")
        
        # Participants Section with detailed information
        lines.append("👥 PARTICIPANTS")
        lines.append("-" * 100)
        for user_id, info in participants.items():
            lines.append(f"• {info['name']}")
            lines.append(f"  ├─ ID: {user_id}")
            lines.append(f"  ├─ Messages: {info['message_count']}")
            if info['roles']:
                lines.append(f"  └─ Roles: {', '.join(info['roles'])}")
            lines.append("")
        
        # Footer with additional information
        lines.append("=" * 100)
        lines.append(f"{'End of Transcript':^100}")
        lines.append("=" * 100)
        lines.append("")
        lines.append("This transcript was automatically generated by the FakePixel Giveaways Ticket System.")
        lines.append("For any questions or concerns, please contact a staff member.")
        
        return "\n".join(lines)

    def _format_size(self, size_bytes):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    async def store_transcript_metadata(self, ticket_number: str, transcript_data: Dict[str, Any]) -> bool:
        """Store transcript metadata"""
        try:
            metadata = {
                "ticket_number": ticket_number,
                "generated_at": datetime.utcnow().isoformat(),
                "text_file": transcript_data.get('text_file'),
                "message_count": transcript_data.get('message_count', 0),
                "participants": transcript_data.get('participants', [])
            }
            
            metadata_file = os.path.join(self.transcript_dir, f"metadata_{ticket_number}.json")
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Stored transcript metadata for ticket {ticket_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing transcript metadata: {e}")
            return False

    async def get_transcript_stats(self) -> Dict[str, Any]:
        """Get statistics about generated transcripts"""
        try:
            total_transcripts = len([f for f in os.listdir(self.transcript_dir) if f.endswith('.json')])
            total_size = sum(os.path.getsize(os.path.join(self.transcript_dir, f)) for f in os.listdir(self.transcript_dir) if f.endswith('.json'))
            
            latest_transcript = max(
                [os.path.join(self.transcript_dir, f) for f in os.listdir(self.transcript_dir) if f.endswith('.json')],
                key=os.path.getctime,
                default=None
            )

            return {
                'total_transcripts': total_transcripts,
                'storage_used': f"{total_size / 1024 / 1024:.2f} MB",
                'last_generated': datetime.fromtimestamp(os.path.getctime(latest_transcript)).isoformat() if latest_transcript else None
            }
        except Exception as e:
            logger.error(f"Error getting transcript stats: {e}")
            return {
                'total_transcripts': 0,
                'storage_used': '0 MB',
                'last_generated': None
            }

    async def cleanup_old_transcripts(self, days: int) -> int:
        """Clean up old transcript files"""
        try:
            cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
            deleted_count = 0

            for filename in os.listdir(self.transcript_dir):
                if not filename.endswith('.json'):
                    continue

                filepath = os.path.join(self.transcript_dir, filename)
                if os.path.getctime(filepath) < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} old transcript files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up transcripts: {e}")
            return 0 