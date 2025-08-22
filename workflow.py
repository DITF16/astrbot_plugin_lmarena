import io
import re
import base64
import random
from pathlib import Path
from typing import Optional

import aiohttp
from PIL import Image

from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
import astrbot.core.message.components as Comp

class ImageWorkflow:
    """
    一个把「下载 / 压缩 / 获取头像 / 生图」串在一起的工具类
    """
    MAX_B64_SIZE = 4_500_000  # 4.5MB

    def __init__(self,base_url: str):
        """
        :param base_url: API 的 base url
        """
        self.base_url = base_url
        self.session = aiohttp.ClientSession()

    async def _download_image(self, url: str, http: bool = True) -> bytes | None:
        """下载图片"""
        if http:
            url = url.replace("https://", "http://")
        try:
            async with self.session.get(url) as resp:
                return await resp.read()
        except Exception as e:
            logger.error(f"图片下载失败: {e}")
            return None

    async def _get_avatar(self, user_id: str) -> bytes | None:
        """根据 QQ 号下载头像"""
        # 简单容错：如果不是纯数字就随机一个
        if not user_id.isdigit():
            user_id = "".join(random.choices("0123456789", k=9))

        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
        try:
            async with self.session.get(avatar_url, timeout=10) as resp:
                resp.raise_for_status()
                return await resp.read()
        except Exception as e:
            logger.error(f"下载头像失败: {e}")
            return None

    def _extract_first_frame(self, raw: bytes) -> bytes:
        """把 GIF 的第一帧抽出来，返回 PNG/JPEG 字节流"""
        img_io = io.BytesIO(raw)
        img = Image.open(img_io)
        if img.format != "GIF":
            return raw  # 不是 GIF，原样返回
        logger.info("检测到GIF, 将抽取 GIF 的第一帧来生图")
        first_frame = img.convert("RGBA")
        out_io = io.BytesIO()
        first_frame.save(out_io, format="PNG")
        return out_io.getvalue()

    def _compress_image(self, image_bytes: bytes, max_bytes: int) -> bytes:
        """
        压缩静态图片到指定大小以内 (按文件体积大小限制)，GIF 不处理
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))

            # GIF 不处理
            if img.format == "GIF":
                return image_bytes

            # 如果原始大小就已经符合要求，直接返回
            if len(image_bytes) <= max_bytes:
                return image_bytes

            output = io.BytesIO()
            quality = 95

            while True:
                output.seek(0)
                output.truncate(0)

                img.save(output, format=img.format, quality=quality, optimize=True)

                # 如果大小符合要求或质量过低，停止
                if output.tell() <= max_bytes or quality <= 30:
                    break
                quality -= 10

            output.seek(0)
            return output.getvalue()

        except Exception as e:
            raise ValueError(f"图片压缩失败: {e}")


    async def _load_bytes(self, src: str) -> bytes | None:
        """统一把 src 转成 bytes"""
        raw: Optional[bytes] = None

        # 1. 本地文件
        if Path(src).is_file():
            raw = Path(src).read_bytes()

        # 2. URL
        elif src.startswith("http"):
            raw = await self._download_image(src)

        # 3. Base64（直接返回）
        elif src.startswith("base64://"):
            return base64.b64decode(src[9:])

        if not raw:
            return None

        # 抽 GIF 第一帧
        raw = self._extract_first_frame(raw)

        return raw


    async def get_first_image(self, event: AstrMessageEvent) -> bytes | None:
        """
        获取消息里的第一张图并以 Base64 字符串返回。
        顺序：
        1) 引用消息中的图片
        2) 当前消息中的图片
        3) 当前消息中的 @ 头像
        找不到返回 None。
        """

        # ---------- 1. 先看引用 ----------
        reply_seg = next(
            (s for s in event.get_messages() if isinstance(s, Comp.Reply)), None
        )
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Comp.Image):
                    if seg.url and (img := await self._load_bytes(seg.url)):
                        return img
                    if seg.file and (img := await self._load_bytes(seg.file)):
                        return img

        # ---------- 2. 再看当前消息 ----------
        for seg in event.get_messages():
            if isinstance(seg, Comp.Image):
                if seg.url and (img := await self._load_bytes(seg.url)):
                    return img
                if seg.file and (img := await self._load_bytes(seg.file)):
                    return img

            elif isinstance(seg, Comp.At) and str(seg.qq) != event.get_self_id():
                if avatar := await self._get_avatar(str(seg.qq)):
                    return avatar

            elif isinstance(seg, Comp.Plain):
                plains = seg.text.strip().split()
                if len(plains) == 2 and plains[1].startswith("@"):
                    if avatar := await self._get_avatar(plains[1][1:]):
                        return avatar

        # 兜底：发消息者自己的头像
        return await self._get_avatar(event.get_sender_id())




    async def generate_image(self, image: bytes, prompt: str, model:str) -> bytes|str|None:
        """
        发送「手办化」请求并返回图片 URL
        """
        logger.info(f"请求生图: {prompt[:50]}...")
        compressed_img = self._compress_image(image, self.MAX_B64_SIZE)
        img_b64 = base64.b64encode(compressed_img).decode()
        url = f"{self.base_url}/v1/chat/completions"
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            },
        ]
        data = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "n": 1,
        }
        headers = {"Content-Type": "application/json"}

        async with self.session.post(url, headers=headers, json=data) as resp:
            result = await resp.json()
            if resp.status != 200:
                logger.error(f"请求失败: {result}")
                message = result.get("error", {}).get("message") or str(result)
                return message

            try:
                content = result["choices"][0]["message"]["content"]
                match = re.search(r"!\[.*?\]\((.*?)\)", content)
                if not match:
                    logger.error("未找到图片 URL")
                    return None
                image_url = match.group(1)
                logger.info(f"手办化图片 URL: {image_url}")
                img = await self._download_image(image_url, http=False)
                return img
            except Exception as e:
                logger.error(f"解析图片失败: {e}")
                return None

    async def terminate(self):
        if self.session:
            await self.session.close()
