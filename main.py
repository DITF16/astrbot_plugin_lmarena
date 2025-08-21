import aiohttp
import re
from astrbot.api.event import filter
from astrbot import logger
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .utils import get_first_image_b64


@register(
    "astrbot_plugin_nano_banana",
    "Zhalslar",
    "对接nano_banana将图片手办化",
    "1.0.0",
)
class NanoBananaPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.save_path = (
            StarTools.get_data_dir("astrbot_plugin_nano_banana") / "generated.png"
        )
        self.base_url = config.get("base_url", "http://127.0.0.1:5102")
        self.headers = {"Content-Type": "application/json"}
        self.model = config.get("model", "nano-banana")
        self.prompt = config.get("prompt", "")
        self.save_image = config.get("save_image", False)

    @filter.command("手办化")
    async def on_message(self, event: AstrMessageEvent):
        """(引用图片)手办化"""
        img_b64 = await get_first_image_b64(event)
        if not img_b64:
            yield event.plain_result("缺少图片参数")
            return
        img_url = await self.generate_image(img_b64)
        if not img_url:
            yield event.plain_result("生成失败")
            return
        yield event.chain_result([Image.fromURL(img_url)])

    async def generate_image(self, img_b64: str) -> str | None:
        """
        发送文生图请求并保存图片
        :param prompt: 文生图提示词
        :param model: 模型名称
        :param filename: 保存的文件名
        :return: 图片文件路径，失败返回 None
        """
        logger.info("开始请求手办化")
        url = f"{self.base_url}/v1/chat/completions"
        content = [
            {"type": "text", "text": self.prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            },
        ]
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "n": 1,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=data) as resp:
                if resp.status != 200:
                    logger.error(f"请求失败:{await resp.text()}")
                    return None

                result = await resp.json()
                try:
                    content = result["choices"][0]["message"]["content"]
                    match = re.search(r"!\[.*?\]\((.*?)\)", content)
                    if not match:
                        logger.error("未找到图片 URL")
                        return None
                    image_url = match.group(1)
                    logger.info(f"手办化图片URL: {image_url}")
                    return image_url

                except Exception as e:
                    logger.error(f"解析图片失败:{e}")
                    return None
