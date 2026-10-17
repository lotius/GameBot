"""Server-local delegation; role assignment always requires Manage Server."""
import asyncio
import logging


async def can_manage_bot(guild, member, store):
    if guild is None:
        return False
    if member.guild_permissions.manage_guild:
        return True
    try:
        role_id = await asyncio.wait_for(asyncio.to_thread(store.get_admin_role, guild.id), timeout=2)
    except Exception:
        logging.warning('Could not verify bot administrator role for guild %s.', guild.id)
        return False
    # Verify current membership each time, including modal submission.
    return type(role_id) is int and any(role.id == role_id for role in getattr(member, 'roles', []))
