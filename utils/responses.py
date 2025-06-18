import datetime
import discord
from typing import Optional
import logging
from . import storage

logger = logging.getLogger(__name__)

def create_embed(title: str, description: str, type: str = "info") -> discord.Embed:
    colors = {
        "success": discord.Color.green(),
        "error": discord.Color.red(),
        "warning": discord.Color.orange(),
        "info": discord.Color.blue()
    }
    
    icons = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️"
    }
    
    embed = discord.Embed(
        title=f"{icons.get(type, '')} {title}",
        description=description,
        color=colors.get(type, discord.Color.blue())
    )
    
    return embed

def error_embed(title: str, description: str) -> discord.Embed:
    """Create an error notification embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def success_embed(title: str, description: str) -> discord.Embed:
    """Create a success notification embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def ticket_embed(user: discord.Member, category: str, ticket_number: str, details: Optional[str] = None, claimed_by: Optional[str] = None) -> discord.Embed:
    """Create a ticket embed message with professional styling"""
    
    # Get category-specific information
    if "Carry" in category:
        title = "Carry Request"
        description = f"Ticket #{ticket_number} • {category}"
        color = storage.get_category_color(category)
    else:
        title = "Support Ticket"
        description = f"Ticket #{ticket_number} • {category}"
        color = storage.get_category_color(category)

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    # Determine claim status display
    if claimed_by and claimed_by != "Unclaimed":
        status_text = f"Claimed by {claimed_by}"
    else:
        status_text = "Awaiting Response"

    # Add ticket information in a clean format
    embed.add_field(
        name="Customer Information",
        value=(
            f"User: {user.mention}\n"
            f"Created: <t:{int(discord.utils.utcnow().timestamp())}:R>\n"
            f"Status: {status_text}"
        ),
        inline=True
    )

    # Add service details if available
    if details:
        # Format details nicely by removing bolding markdown
        formatted_details = details.replace("**", "").replace("*", "")
        embed.add_field(
            name="Service Details",
            value=f"```{formatted_details}```",
            inline=False
        )

    # Add footer with timestamp
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")

    return embed

def feedback_embed(ticket_name: str, user: discord.Member, rating: int, feedback: str, suggestions: str, 
                  claimed_by: Optional[str] = None, closed_by: Optional[str] = None) -> discord.Embed:
    """Create a feedback embed with FakePixel styling"""
    # Determine color based on rating
    if rating >= 4:
        color = discord.Color.green()
        emoji = "🌟"
    elif rating >= 3:
        color = discord.Color.gold()
        emoji = "⭐"
    else:
        color = discord.Color.red()
        emoji = "⚠️"

    embed = discord.Embed(
        title=f"{emoji} Ticket Feedback",
        description=f"**Ticket #{ticket_name}** • **Rating:** {'⭐' * rating}",
        color=color,
        timestamp=datetime.utcnow()
    )

    # Add feedback information
    embed.add_field(
        name="👤 Customer Information",
        value=f"**User:** {user.mention}",
        inline=True
    )

    # Add staff information
    embed.add_field(
        name="👥 Staff Information",
        value=(
            f"**Claimed By:** {claimed_by or 'Unclaimed'}\n"
            f"**Closed By:** {closed_by or 'Unknown'}"
        ),
        inline=True
    )

    # Add feedback details
    embed.add_field(
        name="📝 Feedback",
        value=feedback,
        inline=False
    )

    # Add suggestions if provided
    if suggestions and suggestions.strip():
        embed.add_field(
            name="💡 Suggestions",
            value=suggestions,
            inline=False
        )

    # Add footer
    embed.set_footer(
        text="FakePixel Giveaways • Customer Feedback System",
        icon_url=user.guild.icon.url if user.guild.icon else None
    )

    return embed

def ticket_log_embed(ticket_number: str, creator: discord.Member, category: str, claimed_by: Optional[str] = None, 
                     closed_by: Optional[str] = None, details: Optional[str] = None) -> discord.Embed:
    """Create a ticket log embed with updated format including claim information"""
    logger.info(f"[DEBUG] Creating ticket log embed for ticket {ticket_number}")

    # Determine embed style based on category
    if "Carry" in category:
        title = "📋 Carry Service Completed"
        color = discord.Color.blue()
        emoji = "🎮"
    else:
        title = "📋 Support Ticket Closed"
        color = discord.Color.green()
        emoji = "🎫"

    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=f"**Ticket #{ticket_number}** has been successfully resolved",
        color=color,
        timestamp=datetime.utcnow()
    )

    # Add service information
    embed.add_field(
        name="🎯 Service Information",
        value=(
            f"**Category:** {category}\n"
            f"**Customer:** {creator.mention}\n"
            f"**Status:** ✅ Completed"
        ),
        inline=True
    )

    # Add staff information with claim details
    staff_info = (
        f"**Claimed By:** {claimed_by or 'Unclaimed'}\n"
        f"**Closed By:** {closed_by or 'Unknown'}"
    )
    
    embed.add_field(
        name="👥 Staff Information",
        value=staff_info,
        inline=True
    )

    # Add service details if available
    if details and details.strip():
        # Format details nicely by removing bolding markdown
        formatted_details = details.replace("**", "").replace("*", "")
        embed.add_field(
            name="📝 Service Details",
            value=f"```{formatted_details[:200]}{'...' if len(formatted_details) > 200 else ''}```",
            inline=False
        )

    # Add footer
    embed.set_footer(
        text="FakePixel Giveaways • Service Completion Log",
        icon_url=creator.guild.icon.url if creator.guild.icon else None
    )

    return embed

def create_transcript_embed(ticket_number: str, creator: discord.Member, category: str, 
                        participants: set, start_time: str, end_time: str, 
                        claimed_by: str, closed_by: str, message_count: int) -> discord.Embed:
    """Create an enhanced transcript embed with professional styling and detailed information"""
    # Determine style based on category
    if "Carry" in category:
        title = "📜 Carry Service Transcript"
        color = discord.Color.blue()
        service_type = "Carry Service"
        emoji = "🎮"
    else:
        title = "📜 Support Ticket Transcript"
        color = discord.Color.green()
        service_type = "Support Service"
        emoji = "🎫"

    # Create the main embed
    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=(
            f"**Ticket #{ticket_number}** has been successfully completed\n"
            f"*A detailed record of the service provided*"
        ),
        color=color
    )

    # Add service overview
    embed.add_field(
        name="🎯 Service Overview",
        value=(
            f"**Type:** {service_type}\n"
            f"**Category:** {category}\n"
            f"**Status:** ✅ Completed"
        ),
        inline=True
    )

    # Add customer information
    embed.add_field(
        name="👤 Customer Information",
        value=(
            f"**User:** {creator.mention}\n"
            f"**Created By:** {creator.display_name}"
        ),
        inline=True
    )

    # Add staff information
    embed.add_field(
        name="👥 Staff Information",
        value=(
            f"**Claimed By:** {claimed_by or 'Unclaimed'}\n"
            f"**Closed By:** {closed_by}"
        ),
        inline=True
    )

    # Add conversation statistics
    embed.add_field(
        name="📊 Conversation Statistics",
        value=(
            f"**Total Messages:** {message_count}\n"
            f"**Participants:** {len(participants)}"
        ),
        inline=False
    )

    # Add participants list if not too many
    if len(participants) <= 5:
        participant_list = ", ".join([p.mention if hasattr(p, 'mention') else str(p) for p in participants])
        embed.add_field(
            name="👥 Active Participants",
            value=participant_list,
            inline=False
        )

    # Add footer with professional branding
    embed.set_footer(
        text="FakePixel Giveaways • Professional Service Records",
        icon_url=creator.guild.icon.url if creator.guild.icon else None
    )

    # Add thumbnail if available
    if creator.guild.icon:
        embed.set_thumbnail(url=creator.guild.icon.url)

    return embed

def get_claim_time(claimed_by: str) -> str:
    """Get formatted claim time"""
    if claimed_by and claimed_by != "Unclaimed":
        return f"<t:{int(datetime.utcnow().timestamp())}:R>"
    return "Not claimed"

def format_transcript_log(messages: list, ticket_number: str, claimed_by: str = None) -> str:
    """Format ticket messages into a readable transcript with claim information"""
    log_lines = []
    log_lines.append("=" * 70)
    log_lines.append("FAKEPIXEL GIVEAWAYS - TICKET TRANSCRIPT")
    log_lines.append("=" * 70)
    log_lines.append(f"TICKET NUMBER: #{ticket_number}")
    log_lines.append(f"CLAIMED BY: {claimed_by or 'Unclaimed'}")
    log_lines.append(f"GENERATED: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log_lines.append("=" * 70)
    log_lines.append("")
    
    for msg in messages:
        try:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
            author = msg.author.display_name if hasattr(msg.author, 'display_name') else str(msg.author)
            content = msg.content or "*[attachment or embed]*"
            
            # Clean up content for transcript
            content = content.replace('\n', ' ').strip()
            if len(content) > 100:
                content = content[:97] + "..."
                
            log_lines.append(f"[{timestamp}] {author}: {content}")
        except Exception as e:
            logger.error(f"Error formatting message for transcript: {e}")
            continue
    
    log_lines.append("")
    log_lines.append("=" * 70)
    log_lines.append("END OF TRANSCRIPT")
    log_lines.append("=" * 70)
    
    return "\n".join(log_lines)

def transcript_embed(messages: list, ticket_number: str) -> discord.Embed:
    """Create a transcript embed for the ticket closure with claim information"""
    try:
        # Get creator and category from first message embed
        creator = None
        category = "Unknown"
        claimed_by = "Unclaimed"
        
        # Try to get claim information from storage
        ticket_data = storage.get_ticket_log(ticket_number)
        if ticket_data:
            claimed_by = ticket_data.get('claimed_by', 'Unclaimed')
            category = ticket_data.get('category', 'Unknown')
            creator_id = ticket_data.get('creator_id')
            if creator_id and messages:
                # Try to find creator in message authors
                for msg in messages:
                    if str(msg.author.id) == creator_id:
                        creator = msg.author
                        break
        
        if not creator:
            # Fallback to finding creator from embed mentions
            for msg in messages:
                if msg.embeds and ("New Ticket Created" in msg.embeds[0].title or "New Carry Request" in msg.embeds[0].title or "New Support Ticket" in msg.embeds[0].title):
                    if msg.mentions:
                        creator = msg.mentions[0]
                    
                    # Extract category from embed description or fields
                    embed_desc = msg.embeds[0].description or ""
                    if " - " in embed_desc:
                        category = embed_desc.split(" - ")[-1]
                    break

        # Get participants and message count
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

        # Get start and end times
        start_time = messages[0].created_at if messages else datetime.utcnow()
        end_time = messages[-1].created_at if messages else datetime.utcnow()

        # Get closed by
        closed_by = messages[-1].author.display_name if messages else "Unknown"

        # Create and return the transcript embed with claim information
        return create_transcript_embed(
            ticket_number=ticket_number,
            creator=creator,
            category=category,
            participants=participants,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            claimed_by=claimed_by,
            closed_by=closed_by,
            message_count=len([m for m in messages if not m.author.bot])
        )

    except Exception as e:
        logger.error(f"Error creating transcript embed: {e}")
        # Return a basic error embed with FakePixel branding
        return discord.Embed(
            title="⚠️ Transcript Generation Error",
            description=f"An error occurred while creating the transcript for ticket #{ticket_number}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

def welcome_embed(user: discord.Member, category: str) -> discord.Embed:
    """Create a welcome embed for new tickets"""
    if "Carry" in category:
        title = "🌟 Welcome to FakePixel Giveaways Carry Support! 🌟"
        description = (
            f"Thank you for contacting us, {user.mention}! We're doing our best to help you.\n\n"
            f"**Please note:** We know we're not always on time due to the high volume of carry requests. "
            f"If you're waiting for our help for more than **2 hours**, don't be afraid to click on the "
            f"**📞 Call for Help** button to receive priority assistance from our Staff faster.\n\n"
            f"**Please do this instead of mentioning Staff directly, even if they're online.**"
        )
        color = discord.Color.blue()
    else:
        title = "🎫 Welcome to FakePixel Giveaways Support! 🎫"
        description = (
            f"Thank you for contacting us, {user.mention}! We're here to help you.\n\n"
            f"Our support team will assist you shortly. Please be patient while we review your request.\n\n"
            f"If you need urgent assistance after waiting for a while, you can use the **📞 Call for Help** button."
        )
        color = discord.Color.green()

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    # Add helpful information
    embed.add_field(
        name="📋 What to expect:",
        value=(
            "• Our team will respond as soon as possible\n"
            "• Please provide all necessary details\n"
            "• Be patient - quality service takes time!"
        ),
        inline=False
    )

    # Add footer
    embed.set_footer(
        text="FakePixel Giveaways • Carry Services" if "Carry" in category else "FakePixel Giveaways • Support Services",
        icon_url=None
    )

    # Add thumbnail with the new URL
    embed.set_thumbnail(url='https://drive.google.com/uc?export=view&id=17DOuf9x93haDT9sB-KlSgWgaRJdLQWfo')

    return embed

def claim_notification_embed(ticket_number: str, claimer: discord.Member, action: str) -> discord.Embed:
    """Create an embed for claim/unclaim notifications"""
    if action == "claim":
        title = "✅ Ticket Claimed"
        description = f"Ticket #{ticket_number} has been claimed by {claimer.mention}"
        color = discord.Color.green()
        emoji = "✅"
    else:  # unclaim
        title = "🔄 Ticket Unclaimed"
        description = f"Ticket #{ticket_number} has been unclaimed by {claimer.mention}"
        color = discord.Color.orange()
        emoji = "🔄"

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.add_field(
        name="📋 Ticket Information",
        value=(
            f"**Ticket:** #{ticket_number}\n"
            f"**Action:** {action.title()}\n"
            f"**Staff Member:** {claimer.mention}\n"
            f"**Time:** <t:{int(datetime.utcnow().timestamp())}:R>"
        ),
        inline=False
    )

    embed.set_footer(
        text="FakePixel Giveaways • Ticket Management System",
        icon_url=claimer.guild.icon.url if claimer.guild.icon else None
    )

    return embed

def ticket_stats_embed(ticket_number: str, stats: dict) -> discord.Embed:
    """Create an embed showing detailed ticket statistics with timing information"""
    embed = discord.Embed(
        title="📊 Ticket Statistics",
        description=f"**Detailed statistics for Ticket #{ticket_number}**",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )

    # Basic information
    embed.add_field(
        name="🎫 Basic Information",
        value=(
            f"**Category:** {stats.get('category', 'Unknown')}\n"
            f"**Status:** {stats.get('status', 'Unknown')}\n"
            f"**Claimed By:** {stats.get('claimed_by', 'Unclaimed')}"
        ),
        inline=True
    )

    # Timing information
    response_time = stats.get('response_duration', 0)
    resolution_time = stats.get('resolution_duration', 0)
    
    if response_time > 0:
        response_str = f"{response_time:.1f} seconds"
        if response_time >= 60:
            response_str = f"{response_time/60:.1f} minutes"
        if response_time >= 3600:
            response_str = f"{response_time/3600:.1f} hours"
    else:
        response_str = "No response yet"
    
    if resolution_time > 0:
        resolution_str = f"{resolution_time:.1f} seconds"
        if resolution_time >= 60:
            resolution_str = f"{resolution_time/60:.1f} minutes"
        if resolution_time >= 3600:
            resolution_str = f"{resolution_time/3600:.1f} hours"
    else:
        resolution_str = "Not resolved yet"

    embed.add_field(
        name="⏰ Timing Information",
        value=(
            f"**Response Time:** {response_str}\n"
            f"**Resolution Time:** {resolution_str}\n"
            f"**Created:** <t:{int(discord.utils.parse_time(stats.get('created_at', datetime.utcnow().isoformat())).timestamp())}:R>"
        ),
        inline=True
    )

    # Staff information
    embed.add_field(
        name="👥 Staff Involvement",
        value=(
            f"**Claimer:** {stats.get('claimer_id', 'None')}\n"
            f"**Responder:** {stats.get('responder_id', 'None')}\n"
            f"**Resolver:** {stats.get('resolver_id', 'None')}"
        ),
        inline=False
    )

    embed.set_footer(
        text="FakePixel Giveaways • Performance Analytics",
        icon_url=None
    )

    return embed

def claim_embed(user: discord.Member) -> discord.Embed:
    """Create a claim notification embed"""
    embed = discord.Embed(
        title="Ticket Claimed",
        description=f"Ticket has been claimed by {user.mention}",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def unclaim_embed(user: discord.Member) -> discord.Embed:
    """Create an unclaim notification embed"""
    embed = discord.Embed(
        title="Ticket Unclaimed",
        description=f"Ticket has been unclaimed by {user.mention}",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def close_embed(user: discord.Member, reason: str) -> discord.Embed:
    """Create a ticket close notification embed"""
    embed = discord.Embed(
        title="Ticket Closed",
        description=f"Ticket has been closed by {user.mention}",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    
    if reason:
        embed.add_field(
            name="Reason",
            value=reason,
            inline=False
        )
    
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def transcript_embed(ticket_number: str, text_file: Optional[str] = None) -> discord.Embed:
    """Create a transcript notification embed"""
    embed = discord.Embed(
        title="Ticket Transcript",
        description=f"Transcript for Ticket #{ticket_number}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    if text_file:
        embed.add_field(
            name="Transcript",
            value=f"Text Transcript (attached)",
            inline=False
        )
    
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def setup_embed() -> discord.Embed:
    """Create a setup embed for ticket creation"""
    embed = discord.Embed(
        title="Ticket System",
        description="Select a service to create a ticket",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="Available Services",
        value=(
            "• Slayer Carry\n"
            "• Normal Dungeon Carry\n"
            "• Master Dungeon Carry"
        ),
        inline=False
    )
    
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def help_embed() -> discord.Embed:
    """Create a help embed for ticket commands"""
    embed = discord.Embed(
        title="Ticket Commands",
        description="Available commands for ticket management",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(
        name="Ticket Creation",
        value=(
            "• `/ticket_setup` - Setup ticket system\n"
            "• `/ticket_create` - Create a new ticket"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Ticket Management",
        value=(
            "• `/ticket_close` - Close current ticket\n"
            "• `/ticket_claim` - Claim a ticket\n"
            "• `/ticket_unclaim` - Unclaim a ticket"
        ),
        inline=False
    )
    
    embed.set_footer(text="FakePixel Giveaways", icon_url="https://i.imgur.com/your-logo.png")
    return embed

def create_ticket_embed(ticket_number: str, category: str, description: str, user: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎫 Ticket #{ticket_number}",
        description=f"Category: {category}\n\nDescription:\n{description}",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Created by",
        value=user.mention,
        inline=True
    )
    
    return embed

def create_ticket_list_embed(tickets: list) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Ticket List",
        color=discord.Color.blue()
    )
    
    if not tickets:
        embed.description = "No tickets found."
        return embed
    
    for ticket in tickets:
        embed.add_field(
            name=f"Ticket #{ticket['ticket_number']}",
            value=f"Category: {ticket['category']}\nStatus: {ticket['status']}\nCreated by: <@{ticket['user_id']}>",
            inline=False
        )
    
    return embed

def create_ticket_stats_embed(stats: dict) -> discord.Embed:
    embed = discord.Embed(
        title="📊 Ticket Statistics",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Total Tickets",
        value=str(stats.get('total_tickets', 0)),
        inline=True
    )
    embed.add_field(
        name="Open Tickets",
        value=str(stats.get('open_tickets', 0)),
        inline=True
    )
    embed.add_field(
        name="Closed Tickets",
        value=str(stats.get('closed_tickets', 0)),
        inline=True
    )
    
    return embed

def create_ticket_logs_embed(logs: list) -> discord.Embed:
    embed = discord.Embed(
        title="📝 Recent Ticket Activity",
        color=discord.Color.blue()
    )
    
    if not logs:
        embed.description = "No recent activity found."
        return embed
    
    for log in logs:
        embed.add_field(
            name=f"Ticket {log['ticket_number']}",
            value=f"Action: {log['action']}\nUser: {log['user']}\nTime: {log['timestamp']}",
            inline=False
        )
    
    return embed

def create_ticket_settings_embed(settings: dict) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Ticket System Settings",
        color=discord.Color.blue()
    )
    
    if not settings:
        embed.description = "No settings found."
        return embed
    
    for key, value in settings.items():
        embed.add_field(
            name=key.replace('_', ' ').title(),
            value=str(value),
            inline=True
        )
    
    return embed

def create_ticket_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📚 Ticket System Help",
        description="Here are the available ticket commands:",
        color=discord.Color.blue()
    )
    
    commands = [
        ("/create_ticket", "Create a new support ticket"),
        ("/close_ticket", "Close the current ticket"),
        ("/add_user", "Add a user to the current ticket"),
        ("/remove_user", "Remove a user from the current ticket"),
        ("/rename_ticket", "Rename the current ticket"),
        ("/ticket_info", "View information about the current ticket")
    ]
    
    for cmd, desc in commands:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    return embed

def create_admin_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📚 Admin Commands Help",
        description="Here are the available admin commands:",
        color=discord.Color.blue()
    )
    
    commands = [
        ("/ticket_setup", "Set up the ticket system in the current channel"),
        ("/ticket_stats", "View ticket statistics"),
        ("/purge_tickets", "Delete all closed tickets"),
        ("/backup_tickets", "Create a backup of all ticket data"),
        ("/restore_backup", "Restore ticket data from a backup"),
        ("/ticket_logs", "View recent ticket activity logs"),
        ("/ticket_settings", "Configure ticket system settings"),
        ("/update_settings", "Update ticket system settings")
    ]
    
    for cmd, desc in commands:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    return embed