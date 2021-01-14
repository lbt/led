import asyncio
import itertools

from .StripShow import StripShow
import logging
logger = logging.getLogger(__name__)


class StripController:

    def __init__(self, lamp, strip, config):
        self.strip = strip
        self.lamp = lamp
        lamp.add_handler(self.msg_handler)
        lamp.subscribe("named/control/lamp/#")
        self.strips = {}
        self.shows = {}
        for n in config.keys():
            logger.debug(f"config {n} is {config[n]}")
            ss = strip.createPixelSubStrip(config[n]["first_pixel"],
                                           num=config[n]["num_pixels"])
            self.strips[n] = ss
            show = StripShow(ss)
            self.shows[n] = show
            show.start()
        logger.debug(f"strips {self.strips}")
        logger.debug(f"shows {self.shows}")

    async def msg_handler(self, topic, payload):
        logger.debug(f"Got msg {topic} {payload}")
        if not topic.startswith("named/control/lamp"):
            return False
        topics = topic.split("/")[3:]
        name = topics[0]
        control = topics[1]

        if topics[1] == "brightness":
            self.setBrightness(int(payload))
        elif topics[1] == "strip":
            sname = topics[2]
            painter = topics[3]
            logger.debug(f"Set strip {sname} {painter}")
            await self.shows[sname].setPainter(painter, payload.decode())
        return True
        
    def setBrightness(self, b):
        logger.debug(f"Setting brightness to {b}")
        self.strip.setBrightness(b)
        self.strip.show()
        self.lamp.publish("named/sensor/lamp/Ballroom/brightness", b)

    async def run(self):
        print(self.shows.values())
        asyncio.gather(self.shows.values())

    def exit(self):
        for s in self.shows.keys():
            self.shows[s] = ("colorWipe", Color(0,0,0))
