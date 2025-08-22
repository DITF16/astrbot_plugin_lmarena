

from datetime import datetime
from astrbot.api.event import filter
from astrbot import logger
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .workflow import ImageWorkflow


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
        self.save_image = config.get("save_image", False)
        self.plugin_data_dir = (StarTools.get_data_dir("astrbot_plugin_nano_banana"))
        self.base_url = config.get("base_url", "http://127.0.0.1:5102")
        self.model = config.get("model", "nano-banana")
        self.prompt = config.get("prompt", "")

    async def initialize(self):
        self.iwf = ImageWorkflow(self.base_url)


    @filter.command("手办化")
    async def on_message(self, event: AstrMessageEvent):
        """(引用图片)手办化"""
        img_b64 = await self.iwf.get_first_image_b64(event)

        if not img_b64:
            yield event.plain_result("缺少图片参数")
            return

        res = await self.iwf.generate_image(img_b64, self.prompt, self.model)

        if isinstance(res, bytes):
            yield event.chain_result([Image.fromBytes(res)])
            if self.save_image:
                save_path = (
                    self.plugin_data_dir
                    / f"{self.model}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                )
                with save_path.open("wb") as f:
                    f.write(res)

        elif isinstance(res, str):
            yield event.plain_result(res)

        else:
            yield event.plain_result("生成失败")


    async def terminate(self):
        if self.iwf:
            await self.iwf.terminate()
            logger.info("[ImageWorkflow] session已关闭")

