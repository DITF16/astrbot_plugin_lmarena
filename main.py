from datetime import datetime
from astrbot.api.event import filter
from astrbot import logger
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Image
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from .workflow import ImageWorkflow
from .prompt import prompt_map

@register(
    "astrbot_plugin_lmarena",
    "Zhalslar",
    "对接lmarena调用nano_banana等模型进行生图，如手办化",
    "1.0.4",
)
class LMArenaPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.save_image = config.get("save_image", False)
        self.plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_lmarena")

    async def initialize(self):
        self.iwf = ImageWorkflow(self.conf["base_url"])

    @filter.event_message_type(filter.EventMessageType.ALL, priority=3)
    async def on_lmarena(self, event: AstrMessageEvent):
        """调用lmarena生图"""
        if self.conf["prefix"] and not event.is_at_or_wake_command:
            return

        cmd, _, prompt = event.message_str.partition(" ")
        if cmd not in prompt_map:
            return

        if not prompt or prompt.startswith("@"):
            prompt = prompt_map[cmd]

        img = await self.iwf.get_first_image(event)

        if not img:
            yield event.plain_result("缺少图片参数")
            return

        res = await self.iwf.generate_image(
            image=img,
            prompt=prompt,
            model=self.conf["model"],
            retries=self.conf["retries"],
        )

        if isinstance(res, bytes):
            yield event.chain_result([Image.fromBytes(res)])
            if self.conf["save_image"]:
                save_path = (
                    self.plugin_data_dir
                    / f"{self.conf['model']}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
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
