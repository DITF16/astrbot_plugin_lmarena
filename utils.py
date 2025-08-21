
from random import random
import aiohttp
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import astrbot.core.message.components as Comp
import base64
from pathlib import Path


async def download_image(url: str) -> bytes | None:
    """下载图片"""
    url = url.replace("https://", "http://")
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()
            return img_bytes
    except Exception as e:
        logger.error(f"图片下载失败: {e}")


async def get_avatar(user_id: str) -> bytes | None:
    """下载头像"""
    # if event.get_platform_name() == "aiocqhttp":
    if not user_id.isdigit():
        user_id = "".join(random.choices("0123456789", k=9))
    avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(avatar_url, timeout=10)
            response.raise_for_status()
            return await response.read()
    except Exception as e:
        logger.error(f"下载头像失败: {e}")
        return None




async def get_first_image_b64(event: AstrMessageEvent) -> str | None:
    """
    获取消息里的第一张图并以 Base64 字符串返回。
    顺序：
    1) 引用消息中的图片
    2) 当前消息中的图片
    3) 当前消息中的 @ 头像
    找不到返回 None。
    """

    async def _load_one_b64(src: str) -> str | None:
        """返回 Base64 字符串，失败返回 None"""
        # 1. 本地文件
        if Path(src).is_file():
            return base64.b64encode(Path(src).read_bytes()).decode()

        # 2. URL
        if src.startswith("http"):
            raw = await download_image(src)
            return base64.b64encode(raw).decode() if raw else None

        # 3. Base64（直接去掉前缀即可）
        if src.startswith("base64://"):
            return src[9:]  # 已经是 Base64 字符串，无需再编解码

        return None

    # ---------- 1. 先看引用消息 ----------
    reply_seg = next(
        (s for s in event.get_messages() if isinstance(s, Comp.Reply)), None
    )
    if reply_seg and reply_seg.chain:
        for seg in reply_seg.chain:
            if isinstance(seg, Comp.Image):
                if seg.url and (b64 := await _load_one_b64(seg.url)):
                    return b64
                if seg.file and (b64 := await _load_one_b64(seg.file)):
                    return b64

    # ---------- 2. 再看当前消息 ----------
    for seg in event.get_messages():
        if isinstance(seg, Comp.Image):
            if seg.url and (b64 := await _load_one_b64(seg.url)):
                return b64
            if seg.file and (b64 := await _load_one_b64(seg.file)):
                return b64
        elif isinstance(seg, Comp.At) and str(seg.qq) != event.get_self_id():
            if avatar := await get_avatar(str(seg.qq)):
                return base64.b64encode(avatar).decode()

    return None
