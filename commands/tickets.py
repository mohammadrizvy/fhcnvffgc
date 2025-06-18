import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
from utils.transcript_manager import TranscriptManager
# Import utils
from utils import storage
from utils.views import TicketControlsView, TicketCategoryView
import os
from utils.database import DatabaseManager
from utils.responses import create_embed
from utils.permissions import check_admin_permissions

logger = logging.getLogger('discord')

class TicketCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_categories = ['Slayer Carry', 'Normal Dungeon Carry', 'Master Dungeon Carry', 'Staff Applications']
        logger.info("TicketCommands cog initialized")
        
        # Add message event listener
        self.bot.add_listener(self.on_message, 'on_message')
        self.db = storage.get_db_manager()
        self.transcript_manager = TranscriptManager(bot)

    async def create_ticket_channel(self, interaction: discord.Interaction, category: str, details: Optional[str] = None):
        """Create a ticket channel for the user"""
        try:
            logger.info(f"Creating ticket channel for {interaction.user.name} in category {category}")

            # Create category if it doesn't exist
            category_channel = discord.utils.get(interaction.guild.categories, name=category)
            if not category_channel:
                category_channel = await interaction.guild.create_category(category)
                logger.info(f"Created new category: {category}")

            # Generate ticket number
            ticket_number = await storage.get_next_ticket_number()
            if not ticket_number:
                logger.error("Failed to generate ticket number")
                await interaction.followup.send("Error creating ticket: Failed to generate ticket number", ephemeral=True)
                return None

            logger.info(f"Generated ticket number: {ticket_number}")

            # Get appropriate staff role for the category
            role_name = storage.get_category_role(category)
            staff_role = discord.utils.get(interaction.guild.roles, name=role_name) if role_name else None
            admin_role = discord.utils.get(interaction.guild.roles, name="Admin")

            # Set up channel name with the ticket number
            channel_name = f"ticket-{int(ticket_number):05d}"
            logger.info(f"Generated channel name: {channel_name}")

            # Set up channel permissions
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            # Add staff role permissions
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            # Create ticket channel
            ticket_channel = await category_channel.create_text_channel(
                name=channel_name,
                overwrites=overwrites
            )
            logger.info(f"Created ticket channel: {ticket_channel.name}")

            # Create combined welcome and ticket information embed
            if "Carry" in category:
                title = "🌟 Welcome to FakePixel Giveaways Carry Support! 🌟"
                greeting = (
                    f"Thank you for contacting us, {interaction.user.mention}! We're doing our best to help you.\n\n"
                    f"**Please note:** We know we're not always on time due to the high volume of carry requests. "
                    f"If you're waiting for our help for more than **2 hours**, don't be afraid to click on the "
                    f"**📞 Call for Help** button to receive priority assistance from our Staff faster.\n\n"
                    f"**Please do this instead of mentioning Staff directly, even if they're online.**"
                )
                color = discord.Color.blue()
            else:
                title = "🎫 Welcome to FakePixel Giveaways Support! 🎫"
                greeting = (
                    f"Thank you for contacting us, {interaction.user.mention}! We're here to help you.\n\n"
                    f"Our support team will assist you shortly. Please be patient while we review your request.\n\n"
                    f"If you need urgent assistance after waiting for a while, you can use the **📞 Call for Help** button below."
                )
                color = discord.Color.green()

            # Create the combined embed
            embed = discord.Embed(
                title=title,
                description=greeting,
                color=color,
                timestamp=datetime.utcnow()
            )

            # Add ticket information
            embed.add_field(
                name="🎫 Ticket Information",
                value=(
                    f"**Ticket #:** {ticket_number}\n"
                    f"**Category:** {category}\n"
                    f"**Status:** 🔄 Awaiting Response"
                ),
                inline=True
            )

            # Add helpful information
            embed.add_field(
                name="📋 What to expect:",
                value=(
                    "• Our team will respond as soon as possible\n"
                    "• Please provide all necessary details\n"
                    "• Be patient - quality service takes time!"
                ),
                inline=True
            )

            # Add service details if available
            if details:
                embed.add_field(
                    name="📝 Service Details",
                    value=details,
                    inline=False
                )

            # Add footer
            embed.set_footer(
                text="FakePixel Giveaways • Carry Services",
            )

            # Add thumbnail
            embed.set_thumbnail(url='https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo')

            # Set up controls with claim button
            controls = TicketControlsView(self.bot, ticket_number, initialize_from_db=False)
            control_message = await ticket_channel.send(
                embed=embed,
                view=controls
            )
            controls.message = control_message

            # Send ping to relevant role if it's a carry ticket
            if "Carry" in category:
                carrier_role_name = storage.get_category_role(category)
                if carrier_role_name:
                    carrier_role = discord.utils.get(interaction.guild.roles, name=carrier_role_name)
                    if carrier_role:
                        # Send a simple ping message without duplicating details
                        await ticket_channel.send(
                            content=f"{carrier_role.mention} A new ticket has been created! Please claim it if you are available.",
                            allowed_mentions=discord.AllowedMentions(roles=True)
                        )
                        logger.info(f"Pinged {carrier_role.name} for new {category} ticket {ticket_number}")
                    else:
                        logger.warning(f"Carrier role '{carrier_role_name}' not found for guild {interaction.guild.name}")
                else:
                    logger.warning(f"No carrier role defined for category: {category}")

            # Store ticket information with creation time
            stored = await storage.create_ticket(
                ticket_number=ticket_number,
                user_id=str(interaction.user.id),
                channel_id=str(ticket_channel.id),
                category=category,
                details=details or "",
                guild_id=interaction.guild.id,
                control_message_id=control_message.id
            )
            
            if not stored:
                logger.error(f"Failed to store ticket {ticket_number}")
                await interaction.followup.send("❌ Failed to store ticket information.", ephemeral=True)
                return None
            
            # Set creation time
            await storage.update_ticket_times(ticket_number, "created", str(interaction.user.id))

            # Send confirmation message back to the user in their DM (optional)
            try:
                # Create initial embed for the user
                user_dm_embed = discord.Embed(
                    title="✅ Ticket Created Successfully!",
                    description=f"Your ticket #{ticket_number} in category **{category}** has been created. "
                                f"You can access your ticket channel here: {ticket_channel.mention}",
                    color=discord.Color.green()
                )
                await interaction.user.send(embed=user_dm_embed)
                logger.info(f"Sent DM confirmation to {interaction.user.name} for ticket {ticket_number}")
            except discord.Forbidden:
                logger.warning(f"Could not send DM to {interaction.user.name} for ticket {ticket_number} - DMs closed")

            # Send a response to the interaction to indicate success
            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ Ticket Created",
                    description=f"Your ticket #{ticket_number} has been created in {ticket_channel.mention}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"Ticket {ticket_number} created successfully for {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error creating ticket channel: {e}")
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An error occurred while creating your ticket.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            except Exception as followup_error:
                logger.error(f"Error sending followup message: {followup_error}")

    async def on_message(self, message: discord.Message):
        """Handle messages in ticket channels"""
        try:
            # Ignore bot messages
            if message.author.bot:
                return

            # Check if message is in a ticket channel
            if not message.channel.name.startswith('ticket-'):
                return

            # Get ticket number from channel name
            try:
                ticket_number = message.channel.name.split('-')[1]
            except IndexError:
                return
            
            # Get ticket data
            ticket_data = await storage.get_ticket_log(ticket_number)
            if not ticket_data:
                return

            # Get required role based on category
            category = ticket_data.get('category')
            required_role = storage.get_category_role(category)
            
            if required_role and any(role.name == required_role for role in message.author.roles):
                # Update first response time if this is the first staff response
                await storage.update_ticket_times(ticket_number, "first_response", str(message.author.id))
                logger.info(f"Staff response recorded for ticket {ticket_number} by {message.author.name}")

        except Exception as e:
            logger.error(f"Error in on_message handler: {e}", exc_info=True)

    @app_commands.command(name="close_ticket")
    @app_commands.describe(reason="Reason for closing the ticket")
    async def close_ticket_command(self, interaction: discord.Interaction, reason: str = "Completed"):
        """Close a ticket (Staff only) with enhanced transcript generation"""
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

            # Check if this is a ticket channel
            if not interaction.channel.name.startswith('ticket-'):
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Invalid Channel",
                        description="This command can only be used in ticket channels.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Get ticket number
            try:
                ticket_number = interaction.channel.name.split('-')[1]
            except IndexError:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Could not determine ticket number from channel name.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Get ticket data
            ticket_data = await storage.get_ticket_log(ticket_number)
            if not ticket_data:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="Ticket data not found.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Defer the response since closing might take some time
            await interaction.response.defer(ephemeral=True)

            try:
                # Update ticket times
                await storage.update_ticket_times(ticket_number, "resolved", str(interaction.user.id))
                
                # Close the ticket
                await storage.close_ticket(ticket_number, reason)
                
                # Send closing message with transcript generation info
                await interaction.channel.send(
                    embed=discord.Embed(
                        title="🔒 Ticket Closing",
                        description=(
                            f"This ticket will be deleted in 15 seconds...\n\n"
                            f"**Close Reason:** {reason}\n"
                            f"**Closed by:** {interaction.user.mention}\n\n"
                            f"📋 **Generating enhanced transcript...** Please wait..."
                        ),
                        color=discord.Color.blue()
                    )
                )
                
                # Get all messages from the ticket channel
                messages = []
                async for msg in interaction.channel.history(limit=None, oldest_first=True):
                    messages.append(msg)
                
                # Initialize transcript manager
                transcript_manager = TranscriptManager(self.bot)
                
                # Generate comprehensive transcript (both HTML and text)
                transcript_results = await transcript_manager.generate_comprehensive_transcript(
                    ticket_number, messages, ticket_data
                )
                
                # Get the ticket creator
                creator_id = ticket_data.get('creator_id')
                creator = None
                if creator_id:
                    try:
                        creator = await interaction.guild.fetch_member(int(creator_id))
                    except:
                        logger.warning(f"Could not fetch creator {creator_id} for ticket {ticket_number}")

                # Create enhanced transcript embed with Discord-like styling
                transcript_embed = discord.Embed(
                    title="📋 Enhanced Ticket Transcript",
                    description=f"**Ticket #{ticket_number}** has been closed and archived with full transcript",
                    color=discord.Color.from_rgb(88, 101, 242)  # Discord blurple
                )
                
                # Add ticket information
                transcript_embed.add_field(
                    name="🎫 Ticket Details",
                    value=(
                        f"**Category:** {ticket_data.get('category', 'Unknown')}\n"
                        f"**Creator:** {creator.mention if creator else (f'<@{creator_id}>' if creator_id else 'Unknown')}\n"
                        f"**Claimed By:** {ticket_data.get('claimed_by', 'Unclaimed')}\n"
                        f"**Closed By:** {interaction.user.mention}\n"
                        f"**Close Reason:** {reason}"
                    ),
                    inline=True
                )
                
                # Add statistics
                participants = set(str(msg.author.id) for msg in messages if not msg.author.bot)
                staff_messages = sum(1 for msg in messages if any(role.name in ["Staff", "Admin", "Moderator", "Carrier"] for role in msg.author.roles))
                
                transcript_embed.add_field(
                    name="📊 Conversation Stats",
                    value=(
                        f"**Total Messages:** {len(messages)}\n"
                        f"**Staff Messages:** {staff_messages}\n"
                        f"**User Messages:** {len(messages) - staff_messages}\n"
                        f"**Participants:** {len(participants)}"
                    ),
                    inline=True
                )
                
                # Add timing information
                created_time = ticket_data.get('created_at', 'Unknown')
                if created_time != 'Unknown':
                    try:
                        from datetime import datetime
                        created_dt = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                        duration = datetime.utcnow() - created_dt.replace(tzinfo=None)
                        duration_str = f"{duration.days}d {duration.seconds//3600}h {(duration.seconds//60)%60}m"
                    except:
                        duration_str = "Unknown"
                else:
                    duration_str = "Unknown"
                
                transcript_embed.add_field(
                    name="⏰ Timing Info",
                    value=(
                        f"**Created:** <t:{int(created_dt.timestamp())}:R>\n"
                        f"**Duration:** {duration_str}\n"
                        f"**Closed:** <t:{int(datetime.utcnow().timestamp())}:f>"
                    ),
                    inline=False
                )
                
                # Add transcript links with beautiful formatting
                transcript_links = []
                if transcript_results.get('html_url'):
                    transcript_links.append(f"🌐 **[Discord-Style HTML Transcript]({transcript_results['html_url']})**")
                    transcript_links.append("*Beautiful web interface with Discord styling*")
                
                if transcript_results.get('text_file'):
                    transcript_links.append("📄 **Text Transcript** (attached below)")
                    transcript_links.append("*Traditional format for backup*")
                
                if transcript_links:
                    transcript_embed.add_field(
                        name="🔗 Transcript Access",
                        value="\n".join(transcript_links),
                        inline=False
                    )
                
                # Add service details if available
                details = ticket_data.get('details', '')
                if details and details.strip():
                    # Clean and format details
                    formatted_details = details.replace("**", "").replace("*", "")[:200]
                    if len(formatted_details) == 200:
                        formatted_details += "..."
                    
                    transcript_embed.add_field(
                        name="📝 Service Details",
                        value=f"```{formatted_details}```",
                        inline=False
                    )
                
                # Set thumbnail and footer
                transcript_embed.set_thumbnail(url="https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo")
                transcript_embed.set_footer(
                    text="FakePixel Giveaways • Enhanced Transcript System • Click HTML link for best experience",
                    icon_url="https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo"
                )
                
                transcript_embed.timestamp = datetime.utcnow()
                
                # Prepare files to send
                files = []
                if transcript_results.get('text_file'):
                    filepath = transcript_results['text_file']
                    filename = os.path.basename(filepath) # Extract filename from the path
                    files.append(discord.File(filepath, filename=filename))

                # Send transcript to logs channel if it exists
                transcript_channel = discord.utils.get(interaction.guild.channels, name="ticket-transcripts")
                if transcript_channel:
                    try:
                        logger.info(f"Found transcript channel: {transcript_channel.name} (ID: {transcript_channel.id})")
                        await transcript_channel.send(embed=transcript_embed, files=files)
                        logger.info(f"Sent transcript to logs channel for ticket {ticket_number}")
                    except Exception as e:
                        logger.error(f"Error sending transcript to logs channel: {e}")
                        logger.error(f"Channel permissions: {transcript_channel.permissions_for(interaction.guild.me)}")
                else:
                    logger.error(f"Transcript channel not found in guild {interaction.guild.name} (ID: {interaction.guild.id})")
                    logger.info(f"Available channels: {[c.name for c in interaction.guild.channels]}")

                # Send transcript to the ticket creator
                if creator:
                    try:
                        # Create a user-friendly version of the embed matching the provided image (Top Embed)
                        user_transcript_embed = discord.Embed(
                            title=f"Here's the Ticket {ticket_number} transcript",
                            description=f"{creator.mention}, if you had something important in your ticket or you\n" 
                                        "have faced with some problems while getting help from our Staff, use this\n" 
                                        "transcript which contains of every single message which was sent there.",
                            color=discord.Color.from_rgb(47, 49, 54) # Dark Discord-like color
                        )
                        
                        user_transcript_embed.add_field(
                            name="Ticket was closed with the reason",
                            value=reason,
                            inline=False
                        )
                        
                        user_transcript_embed.set_footer(
                            text="Open the link to see the transcript."
                        )
                        
                        await creator.send(embed=user_transcript_embed)
                        logger.info(f"Sent transcript to creator {creator.name} for ticket {ticket_number}")

                        # Send feedback request to user with transcript file
                        from utils.views import StarRatingView
                        view = StarRatingView(ticket_number, int(creator_id))
                             
                        feedback_request_embed = discord.Embed(
                            title="🌟 Your Feedback Matters! Rate Your Service 🌟",
                            description=(
                                f"Hello **{creator.display_name}**! Your ticket **#{ticket_number}** has been successfully closed.\n\n"
                                "We hope you had an amazing experience with our support team. Your feedback helps us improve and provide even better service!\n\n"
                                "Please take a moment to rate your overall experience below. It's quick, easy, and incredibly valuable to us!"
                            ),
                            color=discord.Color.from_rgb(255, 215, 0)
                        )
                        
                        feedback_request_embed.add_field(
                            name="💡 Why Your Feedback is Important",
                            value="Your ratings and comments help us identify areas of improvement, recognize outstanding staff, and enhance our services for everyone.",
                            inline=False
                        )

                        feedback_request_embed.add_field(
                            name="✅ What Happens Next?",
                            value=(
                                "Once you submit your rating, your feedback will be reviewed by our team. "
                                "Thank you for helping us grow!"
                            ),
                            inline=False
                        )

                        feedback_request_embed.set_footer(
                            text="FakePixel Giveaways • Customer Satisfaction Survey",
                            icon_url="https://i.imgur.com/your-logo.png" # Replace with your logo URL
                        )

                        # Send feedback embed with rating view and transcript file
                        # Ensure the file is a discord.File object
                        transcript_file_to_send = None
                        transcript_filepath = transcript_results.get('text_file')
                        if transcript_filepath and os.path.exists(transcript_filepath):
                            transcript_file_to_send = discord.File(transcript_filepath, filename=os.path.basename(transcript_filepath))

                        await creator.send(
                            embed=feedback_request_embed,
                            view=view,
                            file=transcript_file_to_send
                        )
                        logger.info(f"Sent feedback request to creator {creator.name} for ticket {ticket_number}")

                    except Exception as e:
                        logger.error(f"Error sending transcript or feedback request to creator: {e}")
                        # Fallback for transcript link only
                        try:
                            if transcript_results.get('html_url'):
                                await creator.send(
                                    f"Your ticket #{ticket_number} has been closed.\n"
                                    f"Reason: {reason}\n\n"
                                    f"View your ticket transcript here: {transcript_results['html_url']}"
                                )
                        except:
                            logger.error(f"Failed to send simplified transcript message to creator")

                # Wait 15 seconds before deleting the channel
                await asyncio.sleep(15)
                
                # Delete the channel
                await interaction.channel.delete()
                
                # Send confirmation to the staff member
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="✅ Ticket Closed",
                        description=(
                            f"Ticket #{ticket_number} has been closed successfully.\n\n"
                            f"**Close Reason:** {reason}\n"
                            f"**Transcript:** Sent to logs channel and ticket creator"
                        ),
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
                
            except Exception as e:
                logger.error(f"Error closing ticket: {e}")
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An error occurred while closing the ticket.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in enhanced close ticket command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Error",
                        description="An error occurred while trying to close the ticket.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )

    @app_commands.command(name="ticket_stats")
    @app_commands.describe(ticket_number="The ticket number to get stats for")
    async def ticket_stats(self, interaction: discord.Interaction, ticket_number: str = None):
        """Get statistics for a specific ticket or general stats"""
        try:
            if not any(role.name in ["Staff", "Admin", "Moderator"] for role in interaction.user.roles):
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Permission Denied",
                        description="Only staff members can view ticket statistics.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            if ticket_number:
                # Get specific ticket stats
                ticket_data = await storage.get_ticket(ticket_number)
                if not ticket_data:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Ticket Not Found",
                            description=f"No ticket found with number {ticket_number}",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                    return

                embed = discord.Embed(
                    title=f"📊 Ticket #{ticket_number} Statistics",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )

                embed.add_field(
                    name="Basic Information",
                    value=(
                        f"**Category:** {ticket_data.get('category', 'Unknown')}\n"
                        f"**Status:** {ticket_data.get('status', 'Unknown')}\n"
                        f"**Claimed By:** {ticket_data.get('claimed_by', 'Unclaimed')}"
                    ),
                    inline=True
                )

                # Add timing information if available
                created_at = ticket_data.get('created_at')
                if created_at:
                    embed.add_field(
                        name="Timeline",
                        value=f"**Created:** <t:{int(discord.utils.parse_time(created_at).timestamp())}:R>",
                        inline=True
                    )

            else:
                # Get general statistics
                stats = await storage.get_ticket_statistics()
                
                embed = discord.Embed(
                    title="📊 General Ticket Statistics",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                embed.add_field(
                    name="Overall Stats",
                    value=(
                        f"**Total Tickets:** {stats.get('total_tickets', 0)}\n"
                        f"**Open Tickets:** {stats.get('open_tickets', 0)}\n"
                        f"**Closed Tickets:** {stats.get('closed_tickets', 0)}\n"
                        f"**Claimed Tickets:** {stats.get('claimed_tickets', 0)}"
                    ),
                    inline=True
                )
                
                if stats.get('categories'):
                    category_text = []
                    for category, cat_stats in stats['categories'].items():
                        category_text.append(f"**{category}:** {cat_stats['total']} total ({cat_stats['open']} open)")
                    
                    embed.add_field(
                        name="By Category",
                        value="\n".join(category_text[:5]),  # Limit to 5 categories
                        inline=True
                    )
                
                feedback_info = f"**Total Feedback:** {stats.get('total_feedback', 0)}"
                if stats.get('average_rating'):
                    feedback_info += f"\n**Average Rating:** {stats['average_rating']:.1f}/5.0"
                
                embed.add_field(
                    name="Feedback Stats",
                    value=feedback_info,
                    inline=True
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in ticket_stats command: {e}")
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Error",
                    description="An error occurred while retrieving statistics.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @app_commands.command(name="ticket_setup")
    @app_commands.describe(channel="The channel to set up the ticket system in")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set up the ticket system in a channel"""
        try:
            # Defer the response
            await interaction.response.defer()
            
            # Create the ticket category view
            view = TicketCategoryView()
            
            # Create the embed
            embed = discord.Embed(
                title="🎫 Create a Ticket",
                description=(
                    "Welcome to our ticket system! Please select a category below to create a ticket.\n\n"
                    "**Available Categories:**\n"
                    "• ⚔️ Slayer Carry\n"
                    "• 🏰 Normal Dungeon Carry\n"
                    "• 👑 Master Dungeon Carry\n"
                    "• 📝 Staff Applications\n\n"
                    "Select a category to get started!"
                ),
                color=discord.Color.blue()
            )
            
            # Add thumbnail
            embed.set_thumbnail(url='https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo')
            
            # Send the message with the view
            message = await channel.send(embed=embed, view=view)
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ Ticket system has been set up in {channel.mention}",
                ephemeral=True
            )
            
            logger.info(f"Ticket system set up in channel {channel.name} by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error setting up ticket system: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while setting up the ticket system.",
                    ephemeral=True
                )
            except:
                pass

async def setup(bot):
    await bot.add_cog(TicketCommands(bot))