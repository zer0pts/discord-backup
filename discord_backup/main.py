import discord
import pytz
import sys
from typing import Optional, Union
from datetime import datetime
import os
from pathlib import Path
import logging

# え、zer0ptsはmultinationalなチームだからUTCで生活してるんじゃ……？
tz = pytz.timezone("Asia/Tokyo")

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)
ARCHIVE_COMMAND_PREFIX = "!mochimochi-archive "

client = discord.Client()
token = sys.argv[1]
target_guild = int(sys.argv[2])
target_ch = int(sys.argv[3])

def name_of(x: Union[str, discord.Member]) -> str:
    if isinstance(x, str):
        return x
    elif isinstance(x, (discord.Member, discord.User)):
        return x.display_name
    raise TypeError("unsupported type {}".format(type(x)))

def find_guild_by_id(guild_id: int) -> Optional[discord.Guild]:
    for g in client.guilds:
        if g.id == guild_id:
            return g
    return None

async def find_channel_by_id(g: discord.Guild, channel_id: int) -> Optional[discord.TextChannel]:
    channels = await g.fetch_channels() 
    for ch in channels:
        if ch.id == channel_id:
            return ch
    return None

async def get_emoji(d: Path, emoji: Union[discord.Emoji,discord.PartialEmoji]) -> Path:
    """
    animated gifを使う人は居ないだろからpng決め打ち
    """
    emoji_dir = d.parent.parent / "emojis"
    os.makedirs(emoji_dir, exist_ok=True)
    emoji_path = emoji_dir / (emoji.name + ".png")
    await emoji.url_as(format="png").save(emoji_path)
    return emoji_path

async def get_attachment(d: Path, a: discord.Attachment) -> Path:
    a_dir = d / "attachments"
    os.makedirs(a_dir, exist_ok=True)
    path = a_dir / "{}_{}".format(a.id, a.filename)
    await a.save(path)
    return path

async def format_reaction(d: Path, r: discord.Reaction) -> str:
    users = []
    async for u in r.users():
        users.append(name_of(u))
    if isinstance(r.emoji, (discord.Emoji, discord.PartialEmoji)):
        emoji_path = await get_emoji(d, r.emoji)
        return "![{} by {}]({})".format(r.emoji.name, ",".join(users), os.path.relpath(emoji_path, d))
    elif isinstance(r.emoji, str):
        return "{} by {}".format(r.emoji, ",".join(users))
    else:
        raise TypeError("unsupported type {}".format(type(r.emoji)))


async def format_message(d: Path, msg: discord.Message) -> str:
    # メッセージのformat
    s = """**[{author}](#{id})** {datetime}\n<br/>\n{content}\n<br/>\n""".format(
        id=msg.id,
        author=name_of(msg.author),
        datetime=tz.localize(msg.created_at).strftime("%Y/%m/%d %H:%M:%S%z"),
        content=msg.clean_content,
    )

    # attachment (DLもする)
    for a in msg.attachments:
        path = await get_attachment(d, a)
        if a.content_type and a.content_type.startswith("image"):
            s += "![{}]({})\n<br>\n".format(a.filename, os.path.relpath(path, d))
        else:
            s += "[{}]({})\n<br>\n".format(a.filename, os.path.relpath(path, d))

    # reactions (DLもする）
    for r in msg.reactions:
        r_str = await format_reaction(d, r)
        s += r_str + "\n<br>\n"
    return s

async def archive_channel(directory: Path, channel: discord.TextChannel):
    ch_dir = directory / channel.name
    s = ""
    async for msg in channel.history(limit=None, oldest_first=True):
        s += await format_message(ch_dir, msg)
        s += "\n"

    ch_file = ch_dir / (channel.name + ".md")
    os.makedirs(ch_dir, exist_ok=True)
    with open(ch_file, "w") as f:
        f.write(s)

async def archive_category(directory: Path, category: discord.CategoryChannel):
    cat_dir = directory / category.name
    for ch in category.channels:
        logger.debug("  channel {}".format(ch.name))
        await archive_channel(cat_dir, ch)

async def archive(g: discord.Guild, category_prefix: str):
    # categoryをfilter
    categories = [c for c in g.categories if c.name.lower().startswith(category_prefix)]

    y = datetime.now().strftime("%Y")
    dirname = Path(y) / category_prefix

    # 各カテゴリをアーカイブ
    for c in categories:
        logger.debug("category {}".format(c.name))
        await archive_category(dirname, c)

async def remove(g: discord.Guild, category_prefix: str):
    """
    全てを闇に葬り去る禁忌の関数（いいえ）
    """
    for cat in g.categories:
        if not cat.name.lower().startswith(category_prefix.lower()):
            continue
        for ch in cat.channels:
            await ch.delete()
        await cat.delete()


@client.event
async def on_connect():
    try:
        # 目的のguild / channel を探す
        guild = find_guild_by_id(target_guild)
        if guild is None:
            raise ValueError("no such guilds")
        ch = await find_channel_by_id(guild, target_ch)
        if ch is None:
            raise ValueError("no such channels")

        # bot用のコマンドをたどる
        # 今は直近100件ということにしているけどどうかな
        async for msg in ch.history(limit=100):
            if msg.content.startswith(ARCHIVE_COMMAND_PREFIX):
                logger.debug("got command: {}".format(msg.content))

                prefix = msg.content[len(ARCHIVE_COMMAND_PREFIX):].lower()
                if len(prefix) < 8:
                    await ch.send(":x: too short prefix")
                    continue

                await archive(guild, prefix)
                await ch.send(":white_check_mark: archived {}".format(prefix))

                await remove(guild, prefix)
                await ch.send(":boom: removed {}".format(prefix))

        # 最終的に全ての処理でここにたどり着く
        await client.close()
    except Exception as e:
        await client.close()
        raise e

def main():
    client.run(token)

if __name__ == '__main__':
    main()
