

from datetime import datetime
from astrbot.api.event import filter
from astrbot import logger
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .workflow import ImageWorkflow


@register(
    "astrbot_plugin_lmarena",
    "Zhalslar",
    "对接lmarena调用nano_banana等模型进行生图，如手办化",
    "1.0.3",
)
class LMArenaPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.save_image = config.get("save_image", False)
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_lmarena")
        self.base_url = config.get("base_url", "http://127.0.0.1:5102")
        self.model = config.get("model", "nano-banana")
        self.prompt = config.get("prompt", "")

    async def initialize(self):
        self.iwf = ImageWorkflow(self.base_url)

    @filter.command("nano", alias={"手办化"})
    async def on_nano(self, event: AstrMessageEvent, prompt: str = ""):
        """调用nano_banana生图"""
        img = await self.iwf.get_first_image(event)

        if not img:
            yield event.plain_result("缺少图片参数")
            return

        prompt = prompt if (prompt and not prompt.startswith("@")) else self.prompt
        res = await self.iwf.generate_image(img, prompt, self.model)

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

