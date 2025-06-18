import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime
from . import storage
from .transcript_manager import TranscriptManager
import os
from discord import ui
from typing import Optional, List, Dict, Any
from utils.responses import create_embed

logger = logging.getLogger('discord')

class TicketControlsView(discord.ui.View):
    """Main ticket controls with claim and close buttons"""
    def __init__(self, bot, ticket_number: Optional[str], initialize_from_db: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_number = ticket_number
        self.db = storage.get_db_manager()
        self.transcript_manager = TranscriptManager(bot)
        self.message = None
        self.current_claimer = "Unclaimed"
        self.initialized = False
        
        # Always setup buttons first with default state
        self._setup_buttons()
        
        # Initialize from database if requested
        if initialize_from_db and ticket_number:
            asyncio.create_task(self._initialize_button_state())

    async def _initialize_button_state(self):
        """Initialize button state from database"""
        try:
            ticket_data = await storage.get_ticket_log(self.ticket_number)
            if ticket_data:
                self.current_claimer = ticket_data.get('claimed_by', 'Unclaimed')
            
            # Re-setup buttons with correct state
            self._setup_buttons()
            self.initialized = True
            
            # Update the message if it exists
            if self.message:
                try:
                    await self.message.edit(view=self)
                except Exception as e:
                    logger.error(f"Error updating message after initialization: {e}")
                    
        except Exception as e:
            logger.error(f"Error initializing button state for ticket {self.ticket_number}: {e}")
            self.current_claimer = "Unclaimed"
            self._setup_buttons()
            self.initialized = True

    def _setup_buttons(self):
        """Setup buttons with proper custom IDs for persistence"""
        # Clear existing items
        self.clear_items()
        
        # Determine button state based on current claimer
        if self.current_claimer == "Unclaimed":
            button_label = "Claim Ticket"
            button_style = discord.ButtonStyle.success
            button_emoji = "🙋"
        else:
            button_label = "Claimed"
            button_style = discord.ButtonStyle.danger
            button_emoji = "❌"
        
        # Add claim/unclaim button
        self.claim_button = discord.ui.Button(
            label=button_label,
            style=button_style,
            emoji=button_emoji,
            custom_id=f"claim_{self.ticket_number}",
            row=0
        )
        self.claim_button.callback = self.claim_ticket_callback
        self.add_item(self.claim_button)
        
        # Add call for help button
        self.call_help_button = discord.ui.Button(
            label="📞 Call for Help",
            style=discord.ButtonStyle.secondary,
            custom_id=f"call_help_{self.ticket_number}",
            row=0
        )
        self.call_help_button.callback = self.call_help_callback
        self.add_item(self.call_help_button)
        
        # Add close ticket button
        self.close_button = discord.ui.Button(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id=f"close_{self.ticket_number}",
            row=1
        )
        self.close_button.callback = self.close_ticket_callback
        self.add_item(self.close_button)

    async def update_claim_button_status(self, claimed_by: str):
        """Update the claim button based on current status"""
        self.current_claimer = claimed_by
        
        # Update button properties
        if claimed_by == "Unclaimed":
            self.claim_button.label = "Claim Ticket"
            self.claim_button.style = discord.ButtonStyle.success
            self.claim_button.emoji = "🙋"
        else:
            self.claim_button.label = "Claimed"
            self.claim_button.style = discord.ButtonStyle.danger
            self.claim_button.emoji = "❌"

    async def claim_ticket_callback(self, interaction: discord.Interaction):
        """Handle claim/unclaim ticket button with proper race condition handling"""
        try:
            # Defer the response to prevent timeout
            await interaction.response.defer()
            
            # Get fresh ticket data from database to prevent race conditions
            ticket_data = await storage.get_ticket_log(self.ticket_number)
            if not ticket_data:
                await interaction.followup.send("❌ Ticket not found.", ephemeral=True)
                return

            # Check if user has carrier role for this category
            category = ticket_data.get('category')
            carrier_roles = {
                "Slayer Carry": "Slayer Carrier",
                "Normal Dungeon Carry": "Normal Dungeon Carrier",
                "Master Dungeon Carry": "Master Dungeon Carrier",
                "Staff Applications": "Admin"
            }
            
            required_role = carrier_roles.get(category)
            if not required_role or not any(role.name in [required_role, "Admin", "Staff", "Moderator"] for role in interaction.user.roles):
                await interaction.followup.send(
                    "❌ Only authorized staff can claim tickets for this category.", 
                    ephemeral=True
                )
                return

            # Get current claim status from database (fresh data)
            current_claimer = ticket_data.get('claimed_by', 'Unclaimed')
            
            if current_claimer == "Unclaimed":
                # Try to claim the ticket
                success = await storage.claim_ticket(self.ticket_number, interaction.user.display_name)
                if success:
                    await storage.update_ticket_times(self.ticket_number, "claimed", str(interaction.user.id))
                    
                    # Update button state
                    await self.update_claim_button_status(interaction.user.display_name)
                    
                    # Update the view on the original message
                    await interaction.edit_original_response(view=self)

                    # Update embed
                    await self.update_ticket_embed(interaction, claimed_by=interaction.user.display_name)
                    
                    # Send claim notification
                    embed = discord.Embed(
                        title="✅ Ticket Claimed",
                        description=f"Ticket has been claimed by {interaction.user.mention}",
                        color=discord.Color.green(),
                        timestamp=datetime.utcnow()
                    )
                    await interaction.followup.send(embed=embed)
                    
                    logger.info(f"Ticket {self.ticket_number} claimed by {interaction.user.name}")
                else:
                    await interaction.followup.send("❌ Failed to claim ticket. It may have been claimed by someone else.", ephemeral=True)
                
            elif current_claimer == interaction.user.display_name:
                # Unclaim the ticket
                success = await storage.claim_ticket(self.ticket_number, "Unclaimed")
                if success:
                    # Update button state
                    await self.update_claim_button_status("Unclaimed")
                    
                    # Update the view on the original message
                    await interaction.edit_original_response(view=self)

                    # Update embed
                    await self.update_ticket_embed(interaction, claimed_by="Unclaimed")
                    
                    # Send unclaim notification
                    embed = discord.Embed(
                        title="🔄 Ticket Unclaimed",
                        description=f"Ticket has been unclaimed by {interaction.user.mention}",
                        color=discord.Color.orange(),
                        timestamp=datetime.utcnow()
                    )
                    await interaction.followup.send(embed=embed)
                    
                    logger.info(f"Ticket {self.ticket_number} unclaimed by {interaction.user.name}")
                else:
                    await interaction.followup.send("❌ Failed to unclaim ticket.", ephemeral=True)
                
            else:
                # Someone else has claimed it
                await interaction.followup.send(
                    f"❌ This ticket is already claimed by **{current_claimer}**.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in claim_ticket_callback: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while processing the claim.", 
                    ephemeral=True
                )
            except:
                pass

    async def call_help_callback(self, interaction: discord.Interaction):
        """Handle call for help button"""
        try:
            # Get ticket data
            ticket_data = await storage.get_ticket_log(self.ticket_number)
            if not ticket_data:
                await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
                return

            # Check if ticket has been open for 2 hours
            creation_time = discord.utils.parse_time(ticket_data.get('created_at'))
            current_time = discord.utils.utcnow()
            time_diff = current_time - creation_time
            
            if time_diff.total_seconds() < 7200:  # 2 hours = 7200 seconds
                hours_left = (7200 - time_diff.total_seconds()) / 3600
                await interaction.response.send_message(
                    f"⏰ The **Call for Help** button can only be used after your ticket has been open for **2 hours** with no carrier response.\n\n"
                    f"**Time remaining:** {hours_left:.1f} hours\n\n"
                    f"*Thank you for your patience! Our carriers will get to you as soon as possible.*",
                    ephemeral=True
                )
                return

            # Get the category from ticket data
            category = ticket_data.get('category')
            if not category:
                await interaction.response.send_message("❌ Could not determine ticket category.", ephemeral=True)
                return

            # Define staff roles based on category
            staff_roles = {
                "Slayer Carry": "Slayer Carrier",
                "Normal Dungeon Carry": "Normal Dungeon Carrier",
                "Master Dungeon Carry": "Master Dungeon Carrier",
                "Staff Applications": "Admin", # Staff applications should be handled by admins
            }
            
            role_name = staff_roles.get(category, "Staff") # Default to "Staff" if category not found

            # Get the role object
            target_role = discord.utils.get(interaction.guild.roles, name=role_name)

            if not target_role:
                await interaction.response.send_message(
                    "❌ Staff role for this category not found. Please contact an administrator.",
                    ephemeral=True
                )
                return

            # Notify the relevant staff role
            if interaction.channel:
                await interaction.channel.send(
                    f"{target_role.mention} \n🆘 **{interaction.user.mention}** is requesting assistance with this ticket!", 
                    allowed_mentions=discord.AllowedMentions.roles
                )
                await interaction.response.send_message(
                    f"✅ **{target_role.name}** has been notified! They will be with you shortly.", 
                    ephemeral=True
                )
                logger.info(f"User {interaction.user.name} called for help in ticket {self.ticket_number}")
            else:
                await interaction.response.send_message("❌ Could not send notification in this channel.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in call_help_callback: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while calling for help.", 
                    ephemeral=True
                )
            except:
                pass

    async def close_ticket_callback(self, interaction: discord.Interaction):
        """Handle ticket closing - staff only"""
        try:
            # Check if user has staff permissions
            if not any(role.name in ["Staff", "Admin", "Moderator", "Carrier"] for role in interaction.user.roles):
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Permission Denied",
                        description="Only staff members can close tickets.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Show the close reason modal
            modal = CloseReasonModal(self.ticket_number)
            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error in close ticket callback: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Error",
                            description="An error occurred while trying to close the ticket.",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
            except Exception:
                pass

    async def update_ticket_embed(self, interaction: discord.Interaction, claimed_by: str = None):
        """Update the ticket embed with new claim information"""
        try:
            # Get the original embed from the message
            if not self.message:
                return
                
            embed = self.message.embeds[0] if self.message.embeds else None
            if not embed:
                return
            
            # Use the provided claimed_by or fetch from database
            if claimed_by is None:
                latest_ticket_data = await storage.get_ticket_log(self.ticket_number)
                if latest_ticket_data:
                    claimed_by = latest_ticket_data.get('claimed_by', 'Unclaimed')
                else:
                    claimed_by = 'Unclaimed'
            
            # Find and update the ticket information field
            for i, field in enumerate(embed.fields):
                if "Ticket Information" in field.name:
                    # Get the category from the existing field
                    field_lines = field.value.split('\n')
                    category_line = next((line for line in field_lines if "Category:" in line), "**Category:** Unknown")
                    category = category_line.split('**Category:** ')[1] if '**Category:** ' in category_line else "Unknown"
                    
                    # Update the field value with new claim status
                    status_text = f"✅ Claimed by {claimed_by}" if claimed_by != "Unclaimed" else "🔄 Awaiting Response"
                    field_value = (
                        f"**Ticket #:** {self.ticket_number}\n"
                        f"**Category:** {category}\n"
                        f"**Status:** {status_text}"
                    )
                    embed.set_field_at(i, name=field.name, value=field_value, inline=field.inline)
                    break
            
            # Update the message with new embed
            await self.message.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error updating ticket embed: {e}")

class StarRatingView(discord.ui.View):
    """Star rating system for ticket feedback"""
    def __init__(self, ticket_number: str, user_id: int, timeout: int = 86400):
        super().__init__(timeout=timeout)
        self.ticket_number = ticket_number
        self.user_id = user_id
        self.add_star_buttons()
    
    def add_star_buttons(self):
        """Add star rating buttons"""
        for i in range(1, 6):
            button = discord.ui.Button(
                label=f"{i} ⭐",
                style=discord.ButtonStyle.primary,
                custom_id=f"star_rating_{i}_{self.ticket_number}"
            )
            button.callback = self.create_star_callback(i)
            self.add_item(button)
    
    def create_star_callback(self, rating: int):
        """Create callback for specific rating"""
        async def star_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "This feedback form is not for you.", 
                    ephemeral=True
                )
                return
            
            # Create feedback modal
            modal = FeedbackModal(self.ticket_number, rating, interaction.user)
            await interaction.response.send_modal(modal)
        
        return star_callback
    
    async def on_timeout(self):
        """Handle view timeout"""
        try:
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            logger.info(f"Feedback view timed out for ticket {self.ticket_number}")
        except Exception as e:
            logger.error(f"Error handling view timeout: {e}")

class FeedbackModal(discord.ui.Modal, title="✨ Share Your Experience"):
    def __init__(self, ticket_number: str, rating: int, user: discord.Member):
        super().__init__()
        self.ticket_number = ticket_number
        self.rating = rating
        self.user = user
        self.db = storage.get_db_manager()
        
        if rating >= 4:
            self.title = "✨ Tell us what went well!"
        elif rating >= 3:
            self.title = "💭 Help us understand your experience"
        else:
            self.title = "🔧 Help us improve our service"
        
        # Add feedback field
        self.feedback = discord.ui.TextInput(
            label="Your Experience",
            placeholder="Please share details about your support experience...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            min_length=10
        )
        self.add_item(self.feedback)
        
        # Add suggestions field
        self.suggestions = discord.ui.TextInput(
            label="Suggestions for Improvement",
            placeholder="How can we make our service even better? (Optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        self.add_item(self.suggestions)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        feedback = self.feedback.value
        timestamp = datetime.utcnow()

        ticket_data = await self.db.get_ticket_log(self.ticket_number)

        if not ticket_data:
            await interaction.followup.send("Error: Ticket not found.", ephemeral=True)
            return

        try:
            await self.db.add_feedback(self.ticket_number, self.user.id, self.rating, feedback, timestamp)
            await self.send_thank_you_message(interaction)
            
            # Send feedback to a designated channel
            feedback_channel_id = os.getenv("FEEDBACK_CHANNEL_ID")
            if feedback_channel_id:
                feedback_channel = self.user.guild.get_channel(int(feedback_channel_id))
                if feedback_channel:
                    await self.send_feedback_to_channel(feedback_channel, ticket_data)

        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            await interaction.followup.send("An error occurred while submitting your feedback.", ephemeral=True)

    async def send_feedback_to_channel(self, feedback_channel: discord.TextChannel, ticket_data: dict):
        """Send feedback to the feedback logs channel with enhanced formatting"""
        try:
            # Determine embed color based on rating
            if self.rating >= 4:
                color = discord.Color.green()
                emoji = "🌟"
            elif self.rating >= 3:
                color = discord.Color.gold()
                emoji = "⭐"
            else:
                color = discord.Color.red()
                emoji = "⚠️"

            feedback_embed = discord.Embed(
                title=f"{emoji} Ticket Feedback Received",
                description=f"**Ticket #{self.ticket_number}** • **Overall Rating:** {'⭐' * self.rating}",
                color=color,
                timestamp=datetime.utcnow()
            )
            
            # Add ticket information
            feedback_embed.add_field(
                name="🎫 Ticket Details",
                value=(
                    f"**Category:** {ticket_data.get('category', 'Unknown')}\n"
                    f"**Customer:** {self.user.mention}\n"
                    f"**Claimed By:** {ticket_data.get('claimed_by', 'Unclaimed')}"
                ),
                inline=True
            )
            
            # Add rating info
            feedback_embed.add_field(
                name="📊 Rating",
                value=f"{'⭐' * self.rating} ({self.rating}/5)",
                inline=True
            )
            
            # Add feedback content
            feedback_embed.add_field(
                name="💭 Customer Feedback",
                value=f"```{self.feedback.value}```",
                inline=False
            )
            
            # Add suggestions if provided
            if self.suggestions.value:
                feedback_embed.add_field(
                    name="💡 Suggestions for Improvement",
                    value=f"```{self.suggestions.value}```",
                    inline=False
                )
            
            # Add user avatar as thumbnail
            if self.user.avatar:
                feedback_embed.set_thumbnail(url=self.user.avatar.url)
            
            feedback_embed.set_footer(
                text=f"Feedback ID: {self.ticket_number} • Submitted by {self.user.display_name}",
                icon_url=self.user.avatar.url if self.user.avatar else None
            )
            
            await feedback_channel.send(embed=feedback_embed)
            
        except Exception as e:
            logger.error(f"Error sending feedback to channel: {e}")

    async def send_thank_you_message(self, interaction: discord.Interaction):
        """Send a personalized thank you message to the user"""
        try:
            # Determine the star representation
            stars_display = '⭐' * self.rating + '☆' * (5 - self.rating)

            thank_you_embed = discord.Embed(
                title="Thank you for your rating!",
                description=(
                    f"{interaction.user.mention}, you have successfully rated our Staff's\n" 
                    f"dialog for {stars_display} in Ticket **{self.ticket_number}**. We will for sure improve thanks to\n" 
                    "your reviews!"
                ),
                color=discord.Color.from_rgb(47, 49, 54) # Dark Discord-like color
            )

            # Add feedback comment
            comment_text = self.feedback.value if self.feedback.value else "No comment provided."
            thank_you_embed.add_field(
                name="Here's what you wrote in review:",
                value=f"""```\n{comment_text}\n```""",
                inline=False
            )

            # Set thumbnail from provided image
            thank_you_embed.set_thumbnail(url="https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo")

            # No footer needed as per the image

            await interaction.response.send_message(embed=thank_you_embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error sending thank you message: {e}")
            # Fallback simple message
            try:
                await interaction.response.send_message(
                    "✅ Thank you for your feedback! It has been submitted successfully.",
                    ephemeral=True
                )
            except:
                pass

class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    def __init__(self, ticket_number: str):
        super().__init__()
        self.ticket_number = ticket_number
        self.reason_input = discord.ui.TextInput(
            label="Reason for closing (Optional)",
            style=discord.TextStyle.paragraph,
            placeholder="e.g., Issue resolved, User left, Spam",
            required=False,
            max_length=500
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        close_reason = self.reason_input.value or "No reason provided."

        ticket_commands = interaction.client.get_cog('TicketCommands')
        if ticket_commands:
            await ticket_commands.close_ticket_from_modal(interaction, self.ticket_number, close_reason)
        else:
            await interaction.followup.send("Error: TicketCommands cog not found.", ephemeral=True)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This button can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            ticket_number = channel_name.split("-")[1]
            
            await self.transcript_manager.create_transcript(interaction.channel, ticket_number)
            await interaction.channel.delete()
            
            await self.db.close_ticket(ticket_number)
            
            logger.info(f"Ticket {ticket_number} closed by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error in close_ticket button: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while closing the ticket.",
                    "error"
                ),
                ephemeral=True
            )

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.primary, custom_id="add_user")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This button can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            modal = AddUserModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error in add_user button: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while processing your request.",
                    "error"
                ),
                ephemeral=True
            )

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.secondary, custom_id="remove_user")
    async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This button can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            modal = RemoveUserModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error in remove_user button: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while processing your request.",
                    "error"
                ),
                ephemeral=True
            )

    @discord.ui.button(label="Rename Ticket", style=discord.ButtonStyle.success, custom_id="rename_ticket")
    async def rename_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This button can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            modal = RenameTicketModal()
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error in rename_ticket button: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while renaming the ticket.",
                    "error"
                ),
                ephemeral=True
            )

class AddUserModal(ui.Modal, title="Add User to Ticket"):
    def __init__(self):
        super().__init__()
        self.user_id = ui.TextInput(
            label="User ID",
            placeholder="Enter the user's ID",
            required=True
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            user = interaction.guild.get_member(user_id)
            
            if not user:
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "User not found in the server.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
            
            await interaction.response.send_message(
                embed=create_embed(
                    "Success",
                    f"Added {user.mention} to the ticket.",
                    "success"
                )
            )
            
            logger.info(f"User {user.name} added to ticket {interaction.channel.name} by {interaction.user.name}")
            
        except ValueError:
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "Invalid user ID format.",
                    "error"
                ),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in AddUserModal: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while adding the user.",
                    "error"
                ),
                ephemeral=True
            )

class RemoveUserModal(ui.Modal, title="Remove User from Ticket"):
    def __init__(self):
        super().__init__()
        self.user_id = ui.TextInput(
            label="User ID",
            placeholder="Enter the user's ID",
            required=True
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            user = interaction.guild.get_member(user_id)
            
            if not user:
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "User not found in the server.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            await interaction.channel.set_permissions(user, overwrite=None)
            
            await interaction.response.send_message(
                embed=create_embed(
                    "Success",
                    f"Removed {user.mention} from the ticket.",
                    "success"
                )
            )
            
            logger.info(f"User {user.name} removed from ticket {interaction.channel.name} by {interaction.user.name}")
            
        except ValueError:
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "Invalid user ID format.",
                    "error"
                ),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in RemoveUserModal: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while removing the user.",
                    "error"
                ),
                ephemeral=True
            )

class RenameTicketModal(ui.Modal, title="Rename Ticket"):
    def __init__(self):
        super().__init__()
        self.new_name = ui.TextInput(
            label="New Name",
            placeholder="Enter the new ticket name",
            required=True
        )
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This modal can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            ticket_number = channel_name.split("-")[1]
            new_channel_name = f"ticket-{ticket_number}-{self.new_name.value}"
            
            await interaction.channel.edit(name=new_channel_name)
            
            await interaction.response.send_message(
                embed=create_embed(
                    "Success",
                    f"Ticket renamed to: {new_channel_name}",
                    "success"
                )
            )
            
            logger.info(f"Ticket {ticket_number} renamed to {new_channel_name} by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error in RenameTicketModal: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while renaming the ticket.",
                    "error"
                ),
                ephemeral=True
            )

class TicketCategorySelect(discord.ui.Select):
    """Select menu for ticket categories"""
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Slayer Carry",
                description="Request a Slayer Carry service",
                emoji="⚔️"
            ),
            discord.SelectOption(
                label="Normal Dungeon Carry",
                description="Request a Normal Dungeon Carry service",
                emoji="🏰"
            ),
            discord.SelectOption(
                label="Master Dungeon Carry",
                description="Request a Master Dungeon Carry service",
                emoji="👑"
            ),
            discord.SelectOption(
                label="Staff Applications",
                description="Apply to become a staff member",
                emoji="📝"
            )
        ]
        super().__init__(
            placeholder="Select ticket category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle category selection"""
        try:
            # Defer the response
            await interaction.response.defer()
            
            # Get the selected category
            category = self.values[0]
            
            # Create ticket
            ticket_number = await storage.create_ticket(
                user_id=interaction.user.id,
                category=category,
                guild_id=interaction.guild_id
            )
            
            if not ticket_number:
                await interaction.followup.send(
                    "❌ Failed to create ticket. Please try again later.",
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Add carrier role permissions based on category
            carrier_roles = {
                "Slayer Carry": "Slayer Carrier",
                "Normal Dungeon Carry": "Normal Dungeon Carrier",
                "Master Dungeon Carry": "Master Dungeon Carrier",
                "Staff Applications": "Admin"
            }
            
            required_role = carrier_roles.get(category)
            if required_role:
                role = discord.utils.get(interaction.guild.roles, name=required_role)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Add admin/staff/mod roles
            for role_name in ["Admin", "Staff", "Moderator"]:
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Create the channel
            channel = await interaction.guild.create_text_channel(
                f"ticket-{ticket_number}",
                overwrites=overwrites,
                category=interaction.channel.category
            )
            
            # Create ticket embed
            embed = discord.Embed(
                title=f"Ticket #{ticket_number}",
                description=f"Category: {category}\nCreated by: {interaction.user.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # Add ticket controls
            view = TicketControlsView(interaction.client, ticket_number)
            
            # Send initial message
            await channel.send(
                content=f"{interaction.user.mention} Welcome to your ticket!",
                embed=embed,
                view=view
            )
            
            # Send confirmation to user
            await interaction.followup.send(
                f"✅ Your ticket has been created in {channel.mention}",
                ephemeral=True
            )
            
            logger.info(f"Ticket {ticket_number} created by {interaction.user.name} for category {category}")
            
        except Exception as e:
            logger.error(f"Error in TicketCategorySelect callback: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating your ticket. Please try again later.",
                    ephemeral=True
                )
            except:
                pass

class TicketCategoryView(discord.ui.View):
    """View containing the category select menu"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())