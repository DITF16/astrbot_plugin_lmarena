
import io
from random import random
import aiohttp
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import astrbot.core.message.components as Comp
import base64
from pathlib import Path
from PIL import Image

MAX_B64_SIZE = 4_900_000  # 4.9MB


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

def compress_image(image_io: io.BytesIO, max_size: int = 512) -> io.BytesIO:
    """压缩静态图片到目标大小以内，GIF 不处理"""
    try:
        img = Image.open(image_io)
        output = io.BytesIO()

        if img.format == "GIF":
            # GIF 不压缩，直接返回原图
            image_io.seek(0)
            return image_io

        # 持续缩小尺寸直到小于目标大小
        quality = 95
        while True:
            output.seek(0)
            output.truncate(0)

            # 限制最大宽高
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            img.save(output, format=img.format, quality=quality)
            if output.tell() <= MAX_B64_SIZE or quality <= 30:
                break
            quality -= 10  # 降低质量继续压缩

        output.seek(0)
        return output

    except Exception as e:
        raise ValueError(f"图片压缩失败: {e}")


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
        """返回 Base64 字符串，超过 4.9MB 自动压缩"""
        raw: bytes | None = None

        # 1. 本地文件
        if Path(src).is_file():
            raw = Path(src).read_bytes()

        # 2. URL
        elif src.startswith("http"):
            raw = await download_image(src)

        # 3. Base64（直接返回）
        elif src.startswith("base64://"):
            return src[9:]

        if not raw:
            return None

        # 检查大小是否超过 4.9M
        if len(raw) > MAX_B64_SIZE:
            compressed = compress_image(io.BytesIO(raw))
            raw = compressed.read()

        return base64.b64encode(raw).decode()

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
