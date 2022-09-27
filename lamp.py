#!/usr/bin/env python3
import asyncio
import logging
import toml
from sensor2mqtt import MQController

from lamp.StripPlayer import StripPlayer
from rpi_ws281x import PixelStrip

logger = logging.getLogger(__name__)


class myFormatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__(fmt)

    def format(self, record):
        res = super().format(record)

        if "(task_id)" in res:
            try:
                t = asyncio.current_task()
                n = t.get_name()
            except RuntimeError:
                n = "main"
            res = res.replace("(task_id)", n)

        return res


async def main():
    #asyncio.get_running_loop().set_exception_handler(handle_exception)

    config = toml.load("/home/pi/lamp.toml")
    if "debug" in config and config["debug"]:
        lvl = logging.DEBUG
    else:
        lvl = logging.INFO
    modules = ("__main__",
               "lamp",
#               "sensor2mqtt",
               "microphone",
              )

    ch = logging.StreamHandler()
    ch.setLevel(lvl)
    ch.setFormatter(myFormatter("%(name)s:(task_id) : %(message)s"))
    for l in modules:
        logging.getLogger(l).addHandler(ch)
        logging.getLogger(l).setLevel(lvl)
    logger.debug("Config file loaded:\n%s", config)

    strip = PixelStrip(config["led_count"], config["led_pin"],
                       config["led_freq_hz"], config["led_dma"],
                       config["led_invert"], config["led_brightness"],
                       config["led_channel"])
    strip.begin()

    mqtt_controller = MQController(config)
    strip_player = StripPlayer(mqtt_controller, strip, config["strips"])
    #asyncio.create_task(strip_controller.run())
    await mqtt_controller.run()
    strip_player.exit()

asyncio.run(main(), debug=True)
