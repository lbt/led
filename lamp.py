#!/usr/bin/env python3
import asyncio
import toml
import os
import signal
import logging
import socket

from lamp.LampController import LampController
from lamp.StripController import StripController
from rpi_ws281x import PixelStrip

import logging
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
    logger.debug(f"Config file loaded:\n{config}")

    strip = PixelStrip(config["led_count"], config["led_pin"],
                       config["led_freq_hz"], config["led_dma"],
                       config["led_invert"], config["led_brightness"],
                       config["led_channel"])
    strip.begin()

    lamp = LampController(config)
    strip_controller = StripController(lamp, strip, config["strips"])
    #asyncio.create_task(strip_controller.run())
    await lamp.run()
    strip_controller.exit()

asyncio.run(main(), debug=True)
