import asyncio

from .StripShow import StripShow
import logging
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

    """

    def __init__(self, lamp, strip, config):
        """"""
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
            show = StripShow(self, ss, n)
            self.shows[n] = show
            show.start()
        logger.debug(f"strips {self.strips}")
        logger.debug(f"shows {self.shows}")

    async def msg_handler(self, topic, payload):
        """
        Message format is:
        named/control/lamp/{NAME}/brightness
        named/control/lamp/{NAME}/state
        named/control/lamp/{NAME}/painter
        named/control/lamp/{NAME}/strip/{NAME}/painter/{PAINTER}
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
            if not sname in self.shows:
                logger.alert(f"Strip {sname} not found in lamp {name}")
                return True
            if topics[3] == "painter":
                logger.debug(f"Paint strip {sname} {payload}")
                await self.shows[sname].setPainter(payload)
        return True
        
    def setBrightness(self, b):
        logger.debug(f"Setting brightness to {b}")
        self.strip.setBrightness(b)
        # Now run a frame of the strip show in case it's static
        self.strip.show()
        self.lamp.publish("named/sensor/lamp/Ballroom/brightness", b)

    def publish(self, topic, payload):
        """Publish payload to topic
        Only needs the strip section of the topic
        """
        self.lamp.publish(f"named/sensor/lamp/Ballroom/{topic}", payload)

    async def run(self):
        print(self.shows.values())
        asyncio.gather(self.shows.values())

    def exit(self):
        for s in self.shows.keys():
            self.shows[s] = {"painter": "colorWipe",
                             "colour": (255, 0, 0)}
