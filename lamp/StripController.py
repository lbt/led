import asyncio

from .StripShow import *
from .MusicShow import *
import logging
import json

logger = logging.getLogger(__name__)


class StripController:
    """Paints (Sub)Strips of LEDS controlled by MQTT messages.

    A Strip of LEDs can be split into named SubStrips and each can be
    painted independently using a StripShow.

    The configuration contains sections for each substrip. To create a
    strip called "left" the toml would look like this:
    [strips]
    [strips.left]
    first_pixel = 0
    num_pixels = 140

    A StripShow is an asyncio task that paints the LEDs for a SubStrip.

    When an MQTT message arrives it stops the current StripShow and
    starts a new one.

    The StripController has a number of substrips each of which has an
    associated StripShow. A StripShow can control one or more strips
    so the same show can be present multiple times.
    Equally multiple instances of the same show can be present on
    different strips (typically with different paramaters).
    A show can take over a strip (using the mirror command).

    """

    def __init__(self, mqctrl, strip, config):
        """"""
        self.strip = strip
        self.mqctrl = mqctrl
        mqctrl.add_handler(self.msg_handler)
        mqctrl.subscribe("named/control/lamp/#")
        mqctrl.add_cleanup_callback(self.cleanup)
        self.strips = {}
        self.shows = {}
        for name in config.keys():
            logger.debug(f"config {name} is {config[name]}")
            ss = strip.createPixelSubStrip(config[name]["first_pixel"],
                                           num=config[name]["num_pixels"])
            self.strips[name] = ss
        logger.debug(f"strips {self.strips}")
        self.effects = []

    async def cleanup(self):
        for strip in self.strips.values():
            logger.debug(f"stopping strip {strip}")
            if strip in self.shows:
                show = self.shows[strip]
                logger.debug(f"stopping show {show}")
                await show.removeStrip(strip)
        logger.debug(f"{self} is all cleaned up")

    async def msg_handler(self, topic, payload):
        """
        Message format is:
        named/control/lamp/{NAME}/brightness
        named/control/lamp/{NAME}/state
        named/control/lamp/{NAME}/strip/{NAME}/painter/{PAINTER}
        named/control/lamp/{NAME}/strip/{NAME}/mirror/{NAME2}
        """
        logger.debug(f"Handler got msg {topic} {payload}")
        if not topic.startswith("named/control/lamp"):
            return False
        topics = topic.split("/")[3:]
        name = topics[0]
        control = topics[1]

        if control == "brightness":
            self.setBrightness(int(payload))
        elif control == "state":
            # Don't do on/off atm
            pass
        elif control == "strip":
            sname = topics[2]
            if sname != "all" and sname not in self.strips:
                logger.warning(f"Strip {sname} not found in lamp {name}")
                return True
            if topics[3] == "painter":
                logger.debug(f"Paint strip {sname} {payload}")
                await self.setPainter(sname, payload)
            if topics[3] == "mirror":
                logger.debug(f"Paint strip {sname} {payload}")
                await self.setPainter(payload)
        return True

    async def setPainter(self, sname, rawpayload):
        """Sets the Painter for one or more strips using a json structure.

        The raw payload is interpreted as a utf-8 json string
        containing a hash with a 'painter' key and the args to the
        particular painter.
        """
        logger.debug(f"setPainter({rawpayload})")
        # validate the sname(s) here
        args = json.loads(rawpayload.decode("utf-8") or "null")
        try:
            cls = args["painter"]
        except (TypeError, KeyError):
            logger.debug("No 'painter' found in payload")
            return
        try:
            newshow = globals()[cls](self, args)
        except NameError:
            logger.debug(f"setPainter: invalid painter class: {cls}")

        if sname == "all":
            strips = self.strips.keys()
        else:
            strips = sname.split(",")

        for sname in strips:
            s = self.strips[sname]
            if s in self.shows:
                await self.shows[s].removeStrip(s)
            # Now everything has stopped we can set the global painter and args
            newshow.addStrip(s)
            self.shows[s] = newshow
        newshow.start()

        # self.controller.publish(f"strip/{self.name}/painter",
        #                         self.painter._as_payload())
    
    def setBrightness(self, b):
        logger.debug(f"Setting brightness to {b}")
        self.strip.setBrightness(b)
        # Now run a frame of the strip show in case it's static
        self.strip.show()
        self.mqctrl.publish("named/sensor/lamp/Ballroom/brightness", b)

    def publish(self, topic, payload):
        """Publish payload to topic
        Only needs the strip section of the topic
        """
        self.mqctrl.publish(f"named/sensor/lamp/Ballroom/{topic}", payload)

    def exit(self):
        for s in self.strips.values():
            s.off()
