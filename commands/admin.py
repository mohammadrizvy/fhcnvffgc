import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils import storage
from datetime import datetime
from utils.database import DatabaseManager
from utils.transcript_manager import TranscriptManager
from utils.responses import create_embed
from utils.permissions import check_admin_permissions
from utils.views import (
    CloseReasonModal,
    TicketCategorySelect,
    TicketCategoryView
)

logger = logging.getLogger('discord')

class SetupChannelModal(discord.ui.Modal, title="Set Up Ticket System Channel"):
    """Modal for selecting the channel to set up the ticket system."""
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.channel_input = discord.ui.TextInput(
            label="Channel (ID or #channel-name)",
            placeholder="Enter the ID or mention of the channel (e.g., 123456789012345678 or #tickets)",
            required=True
        )
        self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) # Defer to prevent timeout
        channel_identifier = self.channel_input.value.strip()
        target_channel = None

        try:
            # Try to get channel by ID
            channel_id = int(channel_identifier)
            target_channel = self.bot.get_channel(channel_id)
            if not target_channel:
                target_channel = await self.bot.fetch_channel(channel_id)
        except ValueError:
            # Try to get channel by mention or name
            if channel_identifier.startswith('<#') and channel_identifier.endswith('>'):
                try:
                    channel_id = int(channel_identifier[2:-1])
                    target_channel = self.bot.get_channel(channel_id)
                    if not target_channel:
                        target_channel = await self.bot.fetch_channel(channel_id)
                except ValueError:
                    pass # Not a valid mention, try by name below
            
            if not target_channel:
                # Try to find by name (less reliable)
                for guild in self.bot.guilds:
                    target_channel = discord.utils.get(guild.channels, name=channel_identifier.replace('#', ''))
                    if target_channel: break
        
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                embed=create_embed(
                    "Error",
                    "Invalid channel provided. Please provide a valid channel ID or mention.",
                    "error"
                ),
                ephemeral=True
            )
            return

        try:
            # Create the main embed for the ticket system
            embed = discord.Embed(
                title="🎫 Ticket System",
                description="Welcome to our ticket system! Please select a category below to create a ticket.",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url="https://drive.google.com/uc?export=view&id=1j7S4p2gS9zS5bX_Y9t2f6D3X4y0J9D1") # Replace with your image URL
            
            # Add fields as per the image
            embed.add_field(
                name="⚔️ Slayer Carry",
                value="""• Get help with any slayer task
• Professional slayer assistance
• Fast and efficient service.""",
                inline=False
            )
            embed.add_field(
                name="🏰 Normal Dungeon Carry",
                value="""• Complete any normal dungeon
• Expert guidance
• Guaranteed completion.""",
                inline=False
            )
            embed.add_field(
                name="👑 Master Dungeon Carry",
                value="""• High-level dungeon experts
• Efficient completion times.""",
                inline=False
            )
            
            embed.set_footer(
                text="fakepixle giveaways • Carry Services",
            )

            # Create the view with the dropdown
            view = discord.ui.View(timeout=None) # Main view to hold the select menu
            view.add_item(TicketCategorySelect(self.bot)) # Add the existing dropdown

            await target_channel.send(embed=embed, view=view)
            await interaction.followup.send(
                embed=create_embed(
                    "Success",
                    f"Ticket system has been successfully set up in {target_channel.mention}!",
                    "success"
                ),
                ephemeral=True
            )
            logger.info(f"Ticket system set up in channel {target_channel.name} by {interaction.user.name}")

        except Exception as e:
            logger.error(f"Error setting up ticket system in {target_channel.name}: {e}")
            await interaction.followup.send(
                embed=create_embed(
                    "Error",
                    "An error occurred while setting up the ticket system in the specified channel.",
                    "error"
                ),
                ephemeral=True
            )

class TicketSetupButtonView(discord.ui.View):
    """Initial view with a button to trigger the setup modal."""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Set Up Ticket System", style=discord.ButtonStyle.primary, custom_id="setup_ticket_system_button")
    async def setup_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_admin_permissions(interaction):
            return
        await interaction.response.send_modal(SetupChannelModal(self.bot))

class TicketSetupView(discord.ui.View):
    """Main ticket setup view with dropdown"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketCategorySelect())

class TicketCategorySelect(discord.ui.Select):
    """Dropdown for ticket category selection"""
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label="Slayer Carry",
                description="Get help with any slayer boss carry",
                value="Slayer Carry"
            ),
            discord.SelectOption(
                label="Normal Dungeon Carry", 
                description="Complete any normal dungeon floor",
                value="Normal Dungeon Carry"
            ),
            discord.SelectOption(
                label="Master Dungeon Carry",
                description="Master dungeon floor completion",
                value="Master Dungeon Carry"
            ),
        ]
        super().__init__(
            placeholder="Select a service to create a ticket...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_category = self.values[0]
            logger.info(f"Selected category: {selected_category}")

            # Check if user already has an open ticket
            user_has_ticket = await storage.has_open_ticket(str(interaction.user.id))
            if user_has_ticket:
                existing_channel_id = await storage.get_user_ticket_channel(str(interaction.user.id))
                if existing_channel_id:
                    existing_channel = interaction.guild.get_channel(int(existing_channel_id))
                    if existing_channel:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                title="Ticket Already Exists",
                                description=f"You already have an open ticket: {existing_channel.mention}. Please close your existing ticket before creating a new one.",
                                color=discord.Color.orange()
                            ),
                            ephemeral=True
                        )
                        return

            # Show appropriate modal based on category
            if selected_category == "Slayer Carry":
                modal = SlayerCarryModal(self.bot)
            elif selected_category == "Normal Dungeon Carry":
                modal = NormalDungeonModal(self.bot)
            elif selected_category == "Master Dungeon Carry":
                modal = MasterDungeonModal(self.bot)
            else:
                await interaction.response.send_message(
                    "❌ Invalid category selected.",
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(modal)

        except Exception as e:
            logger.error(f"Error in category selection: {e}")
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request.",
                    ephemeral=True
                )
            except:
                pass

class SlayerCarryModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Slayer Carry Request")
        self.bot = bot
        
        self.in_game_name = discord.ui.TextInput(
            label="What is your in-game username?",
            placeholder="Enter your Minecraft username",
            required=True,
            max_length=16
        )
        self.slayer_type = discord.ui.TextInput(
            label="Which boss do you want to get carried?",
            placeholder="Enter the boss name",
            required=True,
            max_length=50
        )
        self.tier = discord.ui.TextInput(
            label="Which tier?",
            placeholder="Enter the tier number",
            required=True,
            max_length=2
        )
        self.carries = discord.ui.TextInput(
            label="How many times?",
            placeholder="Enter number of carries needed",
            required=True,
            max_length=1
        )
        
        for field in [self.in_game_name, self.slayer_type, self.tier, self.carries]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            carry_details = (
                f"**In-Game Name:** {self.in_game_name.value}\n"
                f"**Slayer Type:** {self.slayer_type.value}\n"
                f"**Tier:** {self.tier.value}\n"
                f"**Number of Carries:** {self.carries.value}"
            )

            ticket_commands = self.bot.get_cog('TicketCommands')
            if ticket_commands:
                await interaction.followup.send("✅ Your slayer carry request has been submitted!", ephemeral=True)
                await ticket_commands.create_ticket_channel(interaction, "Slayer Carry", carry_details)
            else:
                logger.error("TicketCommands cog not found")
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in slayer carry submission: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )
            except:
                pass

class NormalDungeonModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Normal Dungeon Carry Request")
        self.bot = bot
        
        self.in_game_name = discord.ui.TextInput(
            label="What is your in-game username?",
            placeholder="Enter your Minecraft username",
            required=True,
            max_length=16
        )
        self.floor = discord.ui.TextInput(
            label="Which floor?",
            placeholder="Enter floor (F1, F2, F3, F4, F5, F6, F7)",
            required=True,
            max_length=3
        )
        self.completion = discord.ui.TextInput(
            label="S or S+?", 
            placeholder="Enter S or S+",
            required=True,
            max_length=2
        )
        self.carries = discord.ui.TextInput(
            label="How many times? (max 9)",
            placeholder="Enter number of carries needed (1-9)",
            required=True,
            max_length=1
        )
        
        for field in [self.in_game_name, self.floor, self.completion, self.carries]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            carry_details = (
                f"**In-Game Name:** {self.in_game_name.value}\n"
                f"**Floor:** {self.floor.value}\n"
                f"**Completion Type:** {self.completion.value}\n"
                f"**Number of Carries:** {self.carries.value}"
            )

            ticket_commands = self.bot.get_cog('TicketCommands')
            if ticket_commands:
                await interaction.followup.send("✅ Your normal dungeon carry request has been submitted!", ephemeral=True)
                await ticket_commands.create_ticket_channel(interaction, "Normal Dungeon Carry", carry_details)
            else:
                logger.error("TicketCommands cog not found")
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in normal dungeon carry submission: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )
            except:
                pass

class MasterDungeonModal(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Master Dungeon Carry Request")
        self.bot = bot
        
        self.in_game_name = discord.ui.TextInput(
            label="What is your in-game username?",
            placeholder="Enter your Minecraft username",
            required=True,
            max_length=16
        )
        self.floor = discord.ui.TextInput(
            label="Which floor?",
            placeholder="Enter floor (M1, M2, M3, M4, M5, M6, M7)",
            required=True,
            max_length=3
        )
        self.completion = discord.ui.TextInput(
            label="S or S+?", 
            placeholder="Enter S or S+",
            required=True,
            max_length=2
        )
        self.carries = discord.ui.TextInput(
            label="How many times? (max 9)",
            placeholder="Enter number of carries needed (1-9)",
            required=True,
            max_length=1
        )
        
        for field in [self.in_game_name, self.floor, self.completion, self.carries]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            carry_details = (
                f"**In-Game Name:** {self.in_game_name.value}\n"
                f"**Floor:** {self.floor.value}\n"
                f"**Completion Type:** {self.completion.value}\n"
                f"**Number of Carries:** {self.carries.value}"
            )

            ticket_commands = self.bot.get_cog('TicketCommands')
            if ticket_commands:
                await interaction.followup.send("✅ Your master dungeon carry request has been submitted!", ephemeral=True)
                await ticket_commands.create_ticket_channel(interaction, "Master Dungeon Carry", carry_details)
            else:
                logger.error("TicketCommands cog not found")
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in master dungeon carry submission: {e}")
            try:
                await interaction.followup.send(
                    "❌ An error occurred while creating the ticket.",
                    ephemeral=True
                )
            except:
                pass

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = storage.get_db_manager()
        self.transcript_manager = TranscriptManager(bot)
        logger.info("AdminCommands cog initialized")

    @app_commands.command(name="close_ticket", description="Close the current ticket")
    @app_commands.checks.has_permissions(administrator=True)
    async def close_ticket(self, interaction: discord.Interaction):
        try:
            if not await check_admin_permissions(interaction):
                return

            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This command can only be used in ticket channels.",
                        "error"
                    ),
                    ephemeral=True
                )
                return

            ticket_number = channel_name.split("-")[1]
            
            await self.transcript_manager.create_transcript(interaction.channel, ticket_number)
            await interaction.channel.delete()
            
            logger.info(f"Ticket {ticket_number} closed by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error in close_ticket: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while closing the ticket.",
                    "error"
                ),
                ephemeral=True
            )

    @app_commands.command(name="add_user", description="Add a user to the current ticket")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_user(self, interaction: discord.Interaction, user: discord.Member):
        try:
            if not await check_admin_permissions(interaction):
                return

            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This command can only be used in ticket channels.",
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
            
            logger.info(f"User {user.name} added to ticket {channel_name} by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error in add_user: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while adding the user.",
                    "error"
                ),
                ephemeral=True
            )

    @app_commands.command(name="remove_user", description="Remove a user from the current ticket")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_user(self, interaction: discord.Interaction, user: discord.Member):
        try:
            if not await check_admin_permissions(interaction):
                return

            channel_name = interaction.channel.name
            if not channel_name.startswith("ticket-"):
                await interaction.response.send_message(
                    embed=create_embed(
                        "Error",
                        "This command can only be used in ticket channels.",
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
            
            logger.info(f"User {user.name} removed from ticket {channel_name} by {interaction.user.name}")
            
        except Exception as e:
            logger.error(f"Error in remove_user: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Error",
                    "An error occurred while removing the user.",
                    "error"
                ),
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))