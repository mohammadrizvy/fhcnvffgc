import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv
import asyncio
from utils import storage
from utils.views import (
    TicketControlsView,
    TicketCategoryView,
    TicketCategorySelect,
    CloseReasonModal,
    StarRatingView,
    FeedbackModal,
    AddUserModal,
    RemoveUserModal,
    RenameTicketModal
)
from utils.database import DatabaseManager
from utils.transcript_manager import TranscriptManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

load_dotenv()

REQUIRED_CHANNELS = {
    'ticket-transcripts': {
        'description': 'Channel for storing ticket transcripts',
        'permissions': lambda guild: {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    },
    'feedback-logs': {
        'description': 'Channel for ticket feedback logs',
        'permissions': lambda guild: {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    },
    'priority-alerts': {
        'description': 'Channel for high priority ticket alerts',
        'permissions': lambda guild: {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    }
}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

async def setup_commands():
    try:
        from commands.admin import AdminCommands
        from commands.tickets import TicketCommands
        
        # Clear existing commands first
        bot.tree.clear_commands(guild=None)
        
        # Add cogs
        await bot.add_cog(AdminCommands(bot))
        await bot.add_cog(TicketCommands(bot))
        
        # Sync commands for each guild
        for guild in bot.guilds:
            try:
                # Clear existing commands first
                bot.tree.clear_commands(guild=guild)
                # Sync new commands
                synced = await bot.tree.sync(guild=guild)
                logger.info(f"Synced {len(synced)} command(s) for guild {guild.name}")
            except Exception as e:
                logger.error(f"Failed to sync commands for guild {guild.name}: {e}")
        
        # Also sync global commands
        try:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} global command(s)")
        except Exception as e:
            logger.error(f"Failed to sync global commands: {e}")

        logger.info("Commands registered and synced successfully")
        
    except Exception as e:
        logger.error(f"Error setting up commands: {e}")

async def setup_required_channels(guild: discord.Guild):
    try:
        created_channels = []
        for channel_name, config in REQUIRED_CHANNELS.items():
            channel = discord.utils.get(guild.channels, name=channel_name)
            if not channel:
                overwrites = config['permissions'](guild)
                channel = await guild.create_text_channel(
                    name=channel_name,
                    topic=config['description'],
                    overwrites=overwrites
                )
                created_channels.append(channel_name)
                logger.info(f"Created {channel_name} channel in {guild.name}")
            else:
                logger.info(f"Channel {channel_name} already exists in {guild.name}")
        
        if created_channels:
            logger.info(f"Successfully created channels: {', '.join(created_channels)}")
            
    except Exception as e:
        logger.error(f"Error setting up required channels: {e}")

@bot.event
async def on_ready():
    try:
        logger.info(f'Bot is ready: {bot.user.name} (ID: {bot.user.id})')
        logger.info(f'Connected to {len(bot.guilds)} guilds')
        
        # Initialize database first
        bot.db = DatabaseManager()
        await bot.db.connect()
        storage.set_db_manager(bot.db)
        
        # Then set up commands
        await setup_commands()
        
        bot.transcript_manager = TranscriptManager(bot)
        logger.info("Enhanced transcript manager initialized")
        
        logger.info("Registering persistent views...")
        try:
            open_tickets = await bot.db.get_all_open_tickets()
            for ticket in open_tickets:
                ticket_number = ticket.get('ticket_number')
                channel_id = ticket.get('channel_id')
                control_message_id = ticket.get('control_message_id')

                if ticket_number and channel_id and control_message_id:
                    try:
                        channel = bot.get_channel(int(channel_id))
                        if not channel:
                            try:
                                channel = await bot.fetch_channel(int(channel_id))
                            except discord.NotFound:
                                logger.warning(f"Channel {channel_id} not found for ticket {ticket_number}")
                                continue

                        if channel and isinstance(channel, discord.TextChannel):
                            try:
                                message = await channel.fetch_message(int(control_message_id))
                                if message:
                                    view = TicketControlsView(bot, ticket_number, initialize_from_db=True)
                                    view.message = message
                                    bot.add_view(view)
                                    
                                    await asyncio.sleep(0.5)
                                    
                                    logger.info(f"Registered persistent view for ticket {ticket_number}")
                            except discord.NotFound:
                                logger.warning(f"Control message {control_message_id} not found for ticket {ticket_number}")
                    except Exception as e:
                        logger.error(f"Error registering persistent view for ticket {ticket_number}: {e}")
        except Exception as e:
            logger.error(f"Error during persistent view registration: {e}")

        for guild in bot.guilds:
            logger.info(f"Setting up channels for guild: {guild.name}")
            await setup_required_channels(guild)
            
        logger.info("Bot setup complete - All channels and commands ready!")
        
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for tickets | /ticket_setup"
            )
        )
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")

@bot.event
async def on_guild_join(guild):
    try:
        logger.info(f"Joined new guild: {guild.name}")
        await setup_required_channels(guild)
    except Exception as e:
        logger.error(f"Error setting up channels for new guild {guild.name}: {e}")

@bot.event
async def on_command_error(ctx, error):
    try:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Missing Permissions",
                    description="You don't have permission to use this command!",
                    color=discord.Color.red()
                )
            )
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Command Not Found",
                    description="That command doesn't exist!",
                    color=discord.Color.red()
                )
            )
        else:
            logger.error(f"Command error: {str(error)}")
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Error",
                    description=f"An error occurred: {str(error)}",
                    color=discord.Color.red()
                )
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

token = os.getenv('DISCORD_TOKEN')
if not token:
    logger.error("No Discord token found in environment variables. Please set DISCORD_TOKEN in .env file")
    print("Please add your Discord bot token to the .env file")
    exit(1)

if __name__ == "__main__":
    try:
        os.makedirs('transcripts', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        os.makedirs('backups', exist_ok=True)
        
        bot.run(token)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        exit(1)