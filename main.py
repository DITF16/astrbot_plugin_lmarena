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
        self.iwf = ImageWorkflow(self.conf["base_url"], self.conf["model"])

    @filter.event_message_type(filter.EventMessageType.ALL, priority=3)
    async def on_lmarena(self, event: AstrMessageEvent):
        """/lm+文字 | 手办化+图片"""
        if self.conf["prefix"] and not event.is_at_or_wake_command:
            return

        cmd, _, text = event.message_str.partition(" ")
        img = None
        if cmd == "lm":
            text = text.strip()
        elif cmd in prompt_map:
            img = await self.iwf.get_first_image(event)
            logger.info(f"[ImageWorkflow] prompt: {text}")
            if not text or text.startswith("@"):
                text = prompt_map[cmd]
        else:
            return

        res = await self.iwf.get_llm_response(
            text=text,
            image=img,
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

    @filter.command("models")
    async def models(self, event: AstrMessageEvent, index: int = 0):
        "查看模型列表，切换模型"
        ids = await self.iwf.get_models()
        if not ids:
            yield event.plain_result("模型列表为空")
            return
        if 0 < index <= len(ids):
            sel_model = ids[index - 1]
            yield event.plain_result(f"已选择模型：{sel_model}")
            await self.iwf.set_model(sel_model)
            self.conf["model"] = sel_model
            self.conf.save_config()
        else:
            msg = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(ids))
            yield event.plain_result(msg)

    async def terminate(self):
        if self.iwf:
            await self.iwf.terminate()
            logger.info("[ImageWorkflow] session已关闭")
