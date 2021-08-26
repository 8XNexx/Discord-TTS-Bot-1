from __future__ import annotations

import asyncio
from functools import wraps
from typing import (TYPE_CHECKING, Any, Awaitable, Callable, Coroutine,
                    Optional, TypeVar, Union, cast)

import discord
from discord.ext import commands

from .classes import CommonCog, TypedGuildContext
from .funcs import group_by, to_thread
from .views import BoolView, ChannelSelector, CommandView


if TYPE_CHECKING:
    from typing_extensions import ParamSpec

    _R = TypeVar("_R")
    _P = ParamSpec("_P")

error_lookup = {"bool": commands.BadBoolArgument, "TextChannel": commands.ChannelNotFound}

def make_fancy(
    func: Callable[[CommonCog, TypedGuildContext, Any], Awaitable[_R]]
) -> Callable[[CommonCog, TypedGuildContext, Optional[Union[discord.TextChannel, bool]]], Coroutine[Any, Any, Optional[_R]]]:

    async def wrapper(self: CommonCog, ctx: TypedGuildContext, value: Optional[Union[discord.TextChannel, bool]] = None) -> Optional[_R]:
        type_to_convert: str = [*func.__annotations__.values()][1].split(".")[-1]
        if value is not None or ctx.interaction is not None:
            if type(value).__name__ != type_to_convert:
                raise error_lookup[type_to_convert](str(value))

            return await func(self, ctx, value)

        if type_to_convert == "TextChannel":
            select_view = CommandView(ctx)
            for channels in group_by(ctx.guild.text_channels, 25):
                channels = [c for c in channels if c is not None]
                select_view.add_item(ChannelSelector(ctx, channels))

            select_view.message = await ctx.reply("Select a channel!", view=select_view) # type: ignore

        elif type_to_convert == "bool":
            bool_view = BoolView(ctx)
            bool_view.message = await ctx.reply("What do you want to set this to?", view=bool_view) # type: ignore

        else:
            ctx.bot.logger.error(f"Unknown Conversion Type: {type_to_convert}")

    wrapper.__original_func__ = func
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__

    return wrapper

def handle_errors(func: Callable[_P, Awaitable[Optional[_R]]]) -> Callable[_P, Coroutine[Any, Any, Optional[_R]]]:
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> Optional[_R]:
        try:
            return await func(*args, **kwargs)
        except Exception as error:
            if isinstance(error, (asyncio.CancelledError, RecursionError)):
                raise

            self = cast(CommonCog, args[0])
            await self.bot.on_error(func.__name__, error)

        return None
    return wraps(func)(wrapper)

def run_in_executor(func: Callable[_P, _R]) -> Callable[_P, Coroutine[Any, Any, _R]]:
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> Coroutine[Any, Any, _R]:
        return to_thread(func, *args, **kwargs)

    return wraps(func)(wrapper)