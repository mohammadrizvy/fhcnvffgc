import discord
from discord.ext import commands

# Define role names
ADMIN_ROLES = ["Admin", "Administrator", "Owner"]
SUPPORT_ROLES = ["Staff", "Support", "Moderator", "Helper"]

def is_admin():
    async def predicate(ctx):
        return any(role.name in ADMIN_ROLES for role in ctx.author.roles)
    return commands.check(predicate)

def is_support():
    async def predicate(ctx):
        return any(role.name in SUPPORT_ROLES for role in ctx.author.roles)
    return commands.check(predicate)

def check_ticket_permission(ctx):
    """Check if user can manage tickets"""
    return ctx.author.guild_permissions.administrator or any(
        role.name == "Ticket Manager" for role in ctx.author.roles
    )

async def check_admin_permissions(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions for slash commands"""
    if interaction.user.guild_permissions.administrator:
        return True
    
    if any(role.name in ADMIN_ROLES for role in interaction.user.roles):
        return True
    
    await interaction.response.send_message(
        embed=discord.Embed(
            title="❌ Permission Denied",
            description="You need administrator permissions to use this command.",
            color=discord.Color.red()
        ),
        ephemeral=True
    )
    return False