import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from typing import Optional, List
import logging
from . import storage
from .transcript_manager import TranscriptManager
import os
from .responses import create_embed

logger = logging.getLogger(__name__)

class TicketClosingSystem:
    def __init__(self, bot):
        self.bot = bot
        self.transcript_manager = TranscriptManager(bot)
        logger.info("TicketClosingSystem initialized")
    
    async def close_ticket_workflow(self, interaction: discord.Interaction, ticket_number: str, close_reason: str) -> bool:
        """Handle the entire ticket closing process with claim information"""
        try:
            logger.info(f"[Workflow Start] Initiating closure for ticket {ticket_number}")
            
            # Get ticket data
            ticket_data = storage.get_ticket_log(ticket_number)
            if not ticket_data:
                logger.error(f"[Workflow Error] No ticket data found for {ticket_number}")
                return False

            logger.info(f"[Workflow Step] Retrieved ticket data for {ticket_number}")

            # Get all messages from the ticket channel
            messages = await self.get_ticket_messages(interaction.channel)
            logger.info(f"[Workflow Step] Retrieved {len(messages)} messages from ticket {ticket_number}")

            # Prepare log metadata with claim information
            creator_id = ticket_data.get('creator_id') or ticket_data.get('user_id')
            category = ticket_data.get('category', 'Unknown')
            claimed_by = ticket_data.get('claimed_by', 'Unclaimed')
            closed_by = str(interaction.user.id)
            details = ticket_data.get('details', '')
            guild_id = interaction.guild.id

            # Store ticket log with all required information including claim data
            stored = storage.store_ticket_log(
                ticket_number=ticket_number,
                messages=messages,
                creator_id=creator_id,
                category=category,
                claimed_by=claimed_by,
                closed_by=closed_by,
                details=details,
                guild_id=guild_id,
                close_reason=close_reason
            )
            
            if not stored:
                logger.error(f"[Workflow Error] Failed to store ticket log for {ticket_number}")
                return False

            logger.info(f"[Workflow Step] Ticket log stored for {ticket_number}")

            # Generate and send transcript with claim information
            transcript_url = None
            try:
                # Find transcript channel
                transcript_channel = discord.utils.get(interaction.guild.channels, name="ticket-transcripts")
                if transcript_channel:
                    # Generate comprehensive transcript which returns the discord.File object
                    transcript_results = await self.transcript_manager.generate_comprehensive_transcript(
                        ticket_number=ticket_number,
                        messages=messages,
                        ticket_data=ticket_data
                    )
                    
                    transcript_file_path = transcript_results.get('text_file')

                    if transcript_file_path and os.path.exists(transcript_file_path):
                        # Create enhanced transcript embed with claim information
                        transcript_embed = self.create_transcript_embed(ticket_data, messages, interaction.user, close_reason)
                        
                        # Send transcript to channel by opening the file
                        with open(transcript_file_path, "rb") as f:
                            discord_file = discord.File(f, filename=os.path.basename(transcript_file_path))
                            transcript_msg = await transcript_channel.send(
                                embed=transcript_embed,
                                file=discord_file
                            )
                            
                            if transcript_msg.attachments:
                                transcript_url = transcript_msg.attachments[0].url
                                logger.info(f"[Workflow Step] Transcript uploaded: {transcript_url}")
                    else:
                        logger.error(f"[Workflow Error] Transcript file not generated or found for {ticket_number} at {transcript_file_path}")
                        await transcript_channel.send(
                            embed=discord.Embed(
                                title="⚠️ Transcript Generation Error",
                                description=f"Failed to generate or find transcript for ticket #{ticket_number}. File path: `{transcript_file_path}`",
                                color=discord.Color.orange()
                            )
                        )
                else:
                    logger.error("[Workflow Error] Transcript channel not found")
                    
            except Exception as transcript_e:
                logger.error(f"[Workflow Error] Error during transcript generation: {transcript_e}")
                # Send fallback error message to the channel if possible
                try:
                    if transcript_channel:
                        await transcript_channel.send(
                            embed=discord.Embed(
                                title="⚠️ Transcript Generation Error",
                                description=f"An unexpected error occurred during transcript generation for ticket #{ticket_number}. Please check logs.",
                                color=discord.Color.orange()
                            )
                        )
                except Exception as fallback_e:
                    logger.error(f"[Workflow Error] Failed to send transcript generation error message: {fallback_e}")

            # Mark ticket as closed with the provided reason
            storage.close_ticket(ticket_number, close_reason)
            logger.info(f"[Workflow Step] Ticket {ticket_number} marked as closed")

            # Send feedback request to the ticket creator
            try:
                creator = await interaction.guild.fetch_member(int(creator_id))
                if creator:
                    # Create feedback view
                    from .views import TicketControlsView
                    view = TicketControlsView(self.bot, ticket_number)
                    await view.send_feedback_request(creator, ticket_number)
                    logger.info(f"[Workflow Step] Feedback request sent to user {creator.name}")
            except Exception as feedback_e:
                logger.error(f"[Workflow Error] Error sending feedback request: {feedback_e}")

            # Delete the ticket channel
            try:
                # Send a final message before deletion
                await interaction.channel.send(
                    embed=discord.Embed(
                        title="🔒 Ticket Closing",
                        description=f"This ticket will be deleted in 5 seconds...\n\n**Close Reason:** {close_reason}",
                        color=discord.Color.blue()
                    )
                )
                # Wait 5 seconds before deleting
                await asyncio.sleep(5)
                await interaction.channel.delete()
                logger.info(f"[Workflow Step] Ticket channel deleted for {ticket_number}")
            except Exception as delete_e:
                logger.error(f"[Workflow Error] Error deleting ticket channel: {delete_e}")
                return False

            logger.info(f"[Workflow End] Successfully completed closure workflow for ticket {ticket_number}")
            return True

        except Exception as e:
            logger.error(f"[Workflow Critical Error] Unexpected error in close ticket workflow: {e}")
            return False

    def create_transcript_embed(self, ticket_data: dict, messages: List[discord.Message], closed_by: discord.Member, close_reason: str) -> discord.Embed:
        """Create an enhanced transcript embed with claim information"""
        try:
            ticket_number = ticket_data.get('ticket_number', 'Unknown')
            category = ticket_data.get('category', 'Unknown')
            creator_id = ticket_data.get('creator_id', 'Unknown')
            claimed_by = ticket_data.get('claimed_by', 'Unclaimed')
            details = ticket_data.get('details', 'No details provided')
            
            # Get participants
            participants = set()
            staff_messages = 0
            user_messages = 0
            
            for msg in messages:
                if not msg.author.bot:
                    participants.add(msg.author)
                    if any(role.name in ["Staff", "Admin", "Moderator", "Carrier"] for role in msg.author.roles):
                        staff_messages += 1
                    else:
                        user_messages += 1
            
            # Create embed
            embed = discord.Embed(
                title="📋 Ticket Transcript Generated",
                description=f"Ticket #{ticket_number} has been closed and archived",
                color=discord.Color.blue()
            )
            
            # Add ticket information
            embed.add_field(
                name="🎫 Ticket Information",
                value=(
                    f"**Category:** {category}\n"
                    f"**Creator:** {creator_id}\n"
                    f"**Claimed By:** {claimed_by}\n"
                    f"**Closed By:** {closed_by.mention}\n"
                    f"**Close Reason:** {close_reason}"
                ),
                inline=True
            )
            
            # Add statistics
            embed.add_field(
                name="📊 Statistics",
                value=(
                    f"**Total Messages:** {len(messages)}\n"
                    f"**Staff Messages:** {staff_messages}\n"
                    f"**User Messages:** {user_messages}\n"
                    f"**Participants:** {len(participants)}"
                ),
                inline=True
            )
            
            # Add ticket details if available
            if details and details != "No details provided":
                embed.add_field(
                    name="📝 Ticket Details",
                    value=f"```{details[:200]}{'...' if len(details) > 200 else ''}```",
                    inline=False
                )
            
            # Add participants list
            if participants:
                embed.add_field(
                    name="👥 Participants",
                    value=", ".join(list(participants)[:10]) + ("..." if len(participants) > 10 else ""),
                    inline=False
                )
            
            embed.set_footer(
                text=f"Ticket System • Closed by {closed_by.display_name}",
                icon_url=closed_by.avatar.url if closed_by.avatar else None
            )
            
            return embed
            
        except Exception as e:
            logger.error(f"Error creating transcript embed: {e}")
            # Return basic embed on error
            return discord.Embed(
                title="📋 Ticket Transcript",
                description=f"Transcript for ticket #{ticket_data.get('ticket_number', 'Unknown')}",
                color=discord.Color.blue()
            )

    async def get_ticket_messages(self, channel: discord.TextChannel) -> List[discord.Message]:
        """Retrieve all messages from a ticket channel"""
        try:
            messages = []
            async for message in channel.history(limit=None, oldest_first=True):
                messages.append(message)
            logger.info(f"Retrieved {len(messages)} messages from channel {channel.name}")
            return messages
        except Exception as e:
            logger.error(f"Error retrieving messages from {channel.name}: {e}")
            return []

class TicketCloser:
    def __init__(self, bot, database_manager, transcript_manager):
        self.bot = bot
        self.db = database_manager
        self.transcript_manager = transcript_manager

    async def close_ticket(self, channel, user, reason=None):
        try:
            ticket_number = channel.name.split('-')[1]
            ticket = self.db.get_ticket(ticket_number)
            
            if not ticket:
                await channel.send(embed=create_embed(
                    "Error",
                    "Ticket not found in database.",
                    "error"
                ))
                return False

            if ticket['status'] == 'closed':
                await channel.send(embed=create_embed(
                    "Error",
                    "This ticket is already closed.",
                    "error"
                ))
                return False

            await channel.send(embed=create_embed(
                "Closing Ticket",
                "This ticket will be closed in 5 seconds...",
                "warning"
            ))

            await asyncio.sleep(5)

            transcript = await self.transcript_manager.create_transcript(channel)
            if transcript:
                self.transcript_manager.save_transcript(ticket_number, transcript)

            if self.db.close_ticket(ticket_number):
                await channel.send(embed=create_embed(
                    "Ticket Closed",
                    f"Ticket #{ticket_number} has been closed by {user.mention}.\nReason: {reason or 'No reason provided'}",
                    "success"
                ))

                await asyncio.sleep(5)
                await channel.delete()
                return True
            else:
                await channel.send(embed=create_embed(
                    "Error",
                    "Failed to close ticket in database.",
                    "error"
                ))
                return False

        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await channel.send(embed=create_embed(
                "Error",
                "An error occurred while closing the ticket.",
                "error"
            ))
            return False

    async def force_close_ticket(self, channel, user, reason=None):
        try:
            ticket_number = channel.name.split('-')[1]
            ticket = self.db.get_ticket(ticket_number)
            
            if not ticket:
                await channel.send(embed=create_embed(
                    "Error",
                    "Ticket not found in database.",
                    "error"
                ))
                return False

            transcript = await self.transcript_manager.create_transcript(channel)
            if transcript:
                self.transcript_manager.save_transcript(ticket_number, transcript)

            if self.db.close_ticket(ticket_number):
                await channel.send(embed=create_embed(
                    "Ticket Force Closed",
                    f"Ticket #{ticket_number} has been force closed by {user.mention}.\nReason: {reason or 'No reason provided'}",
                    "warning"
                ))

                await asyncio.sleep(3)
                await channel.delete()
                return True
            else:
                await channel.send(embed=create_embed(
                    "Error",
                    "Failed to close ticket in database.",
                    "error"
                ))
                return False

        except Exception as e:
            logger.error(f"Error force closing ticket: {e}")
            await channel.send(embed=create_embed(
                "Error",
                "An error occurred while force closing the ticket.",
                "error"
            ))
            return False

    async def close_inactive_tickets(self, days=7):
        try:
            tickets = self.db.get_open_tickets()
            closed_count = 0
            
            for ticket in tickets:
                created_at = datetime.fromisoformat(ticket['created_at'])
                if (datetime.now() - created_at).days >= days:
                    channel = self.bot.get_channel(ticket['channel_id'])
                    if channel:
                        if await self.force_close_ticket(channel, self.bot.user, f"Inactive for {days} days"):
                            closed_count += 1
            
            return closed_count
        except Exception as e:
            logger.error(f"Error closing inactive tickets: {e}")
            return 0