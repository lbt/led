import asyncio
import hashlib
import json
import logging
from typing import Dict, Any

from .StripShow import *
from .MusicShow import *

logger = logging.getLogger(__name__)

class HStrip:
    """Helper class that encapsulates the Strip state
    """

    def __init__(self, name, strip, config):
        self.name = name
        self.strip = strip
        self.first_pixel = config[name]["first_pixel"]
        self.num_pixels = config[name]["num_pixels"]
        self.ss = strip.createPixelSubStrip(self.first_pixel,
                                            num=self.num_pixels)
        # We store the config and hash of each config
        self._quiet = None
        self.quiet_h = None
        self._music = None
        self.music_h = None
        self.current_show = None

    @property
    def quiet(self):
        return self._quiet

    @quiet.setter
    def quiet(self, val):
        assert val is not None
        self._quiet = val
        self.quiet_h = self.dict_hash(val)

    @property
    def music(self):
        return self._music

    @music.setter
    def music(self, val):
        self._music = val
        if val is not None:
            self.music_h = self.dict_hash(val)
        else:
            self.music_h = None

    # https://www.doc.ic.ac.uk/~nuric/coding/how-to-hash-a-dictionary-in-python.html
    def dict_hash(self, dictionary: Dict[str, Any]) -> str:
        """MD5 hash of a dictionary."""
        dhash = hashlib.md5()
        # We need to sort arguments so {'a': 1, 'b': 2} is
        # the same as {'b': 2, 'a': 1}
        encoded = json.dumps(dictionary, sort_keys=True).encode()
        dhash.update(encoded)
        return dhash.hexdigest()


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
        self.name = config['name']
        self.strip = strip
        self.mqctrl = mqctrl
        mqctrl.add_handler(self.msg_handler)
        mqctrl.subscribe(f"named/control/lamp/{self.name}/#")
        mqctrl.subscribe("mpd/pine/player")
        mqctrl.add_cleanup_callback(self.cleanup)
        self.strips = {}
        # shows contains the actual running show Class instance keyed
        # on the config of the instance
        self.shows = {}
        for sname in config.keys():
            if isinstance(config[sname], dict):
                self.strips[sname] = HStrip(sname, strip, config)
        logger.debug(f"strips {self.strips}")
        self.effects = []
        self.music_playing = False
        self._state = True

    async def cleanup(self):
        for show in self.shows.values():
            logger.debug(f"stopping show {show}")
            await show.stop()

        # for strip in self.strips.values():
        #     logger.debug(f"stopping strip {strip}")
        #     if strip.ss in self.shows:
        #         show = self.shows[strip.ss]
        #         logger.debug(f"stopping show {show}")
        #         await show.removeStrip(strip.ss)
        logger.debug(f"{self} is all cleaned up")

    async def msg_mpd_handler(self, topic, rawpayload):
        """
        Message format is:
        mpd/<host>/player
        """
        logger.debug("Handler got mpd msg")
        payload = json.loads(rawpayload)
        try:
            state = payload["status"]["state"]
        except KeyError:
            logger.debug("No status/state in payload")
            return False

        if state == "play":
            if not self.music_playing:
                logger.debug(f"Music_playing was {self.music_playing} => True")
                self.music_playing = True
        else:
            if self.music_playing:
                logger.debug(f"Music_playing was {self.music_playing} => False")
                self.music_playing = False

        for sname in self.strips.keys():
            await self.setPainter(sname)

        logger.debug("Music_playing handled")
        return True

    async def msg_handler(self, topic, rawpayload):
        """
        Message format is:
        named/control/lamp/{NAME}/brightness
        named/control/lamp/{NAME}/state
        # named/control/lamp/{NAME}/strip/{NAME}/painter/{PAINTER}
        # named/control/lamp/{NAME}/strip/{NAME}/mirror/{NAME2}
        # named/control/lamp/{NAME}/state
        named/control/lamp/{NAME}
        {
         state: boolean
         brightness: 0-255
         pixels: <n>
         strips: {
          <strip_name>: {
            first_pixel: <n>
            pixels: <n>
            painter : {
                name: "",
                key: "val"...
            },
            music_painter : {
                name: "",
                key: "val"...
            },
         ],
         ...
        }
        # named/control/lamp/{NAME}/strip/{NAME}/mirror/{NAME2}

        """
        logger.debug(f"Handler got msg {topic}")
        if topic == "mpd/pine/player":
            return await self.msg_mpd_handler(topic, rawpayload)
        if not topic.startswith("named/control/lamp"):
            return False
        logger.debug(f"rawpayload {rawpayload}")
        topics = topic.split("/")[3:]
        name = topics[0]

        if name != self.name:
            logger.debug(f"Message is for {name}, not me {self.name}")
            return False

        # Handle an incoming .../<name>/strip/<strip>|all/painter msg
        # by creating one or more
        #   { "strips": { "<strip>": { <payload> }}}
        try:
            if len(topics) == 5:  # <NAME>/strip/<sname>/<painter|music_painter>/arg
                payload = {"strips":
                           {topics[2]:
                            {topics[3]:
                             {topics[4]: rawpayload.decode("utf-8")}}}}
            elif len(topics) == 4:   # <NAME>/strip/<sname>/<painter|music_painter>
                payload = {"strips":
                           {topics[2]:
                            {topics[3]:
                             json.loads(rawpayload.decode("utf-8") or "null")}}}
            elif len(topics) == 3:   # <NAME>/strip/<sname>
                payload = {"strips":
                           {topics[2]:
                            json.loads(rawpayload.decode("utf-8") or "null")}}
            elif len(topics) == 2:    # <NAME>/<attr>
                attr = topics[1]
                if attr in ["brightness", "state"]:
                    # named/control/lamp/{NAME}/<attr> (brightness or state)
                    val = rawpayload.decode("utf-8") or "None"
                    payload = {attr: val}
                else:
                    logger.debug(f"Unknown attribute {attr}")
                    return False
            elif len(topics) == 1:  # {NAME}
                payload = json.loads(rawpayload.decode("utf-8") or "null")
            logger.debug(f"Converted to {payload}")
        except json.JSONDecodeError:
            logger.warning("Error decoding 'strip' payload")
            return False

        # payload is now a dict of things to do
        if "state" in payload:
            await self.setState(payload["state"])
        if "brightness" in payload:
            await self.setBrightness(int(payload["brightness"]))
        if "pixels" in payload:
            logger.warning("pixels attr is readonly")
        if "strips" in payload:
            strips = payload["strips"]
            for sname, info in strips.items():
                if "pixels" in info:
                    logger.warning(f"Trying to create substrip with {info['pixels']} pixels. Not yet implemented")
                if sname != "all" and sname not in self.strips:
                    logger.warning(f"Strip {sname} not found in lamp {name}")
                    return True
                if sname == "all":
                    for sname in self.strips.keys():
                        logger.debug(f"Paint strip {sname} {info}")
                        await self.storePainter(sname, info)
                else:
                    await self.storePainter(sname, info)

        self.publishState()
        return True

    async def storePainter(self, sname, args):
        """Sets the Painter for one or more strips using a json structure.

        args is a hash with 'painter' and maybe 'music_painter' keys
        and the args to the particular painter.

        """
        logger.debug(f"storePainter({sname}, {args})")
        # validate here
        music = args.get("music_painter", None)
        try:
            quiet = args.get("painter", None)
            # validate the cls here
        except (TypeError, KeyError):
            logger.debug("No 'painter' found in payload")
            return

        # validate the json. Ideally call the painter
        if music:
            if "name" not in music:
                logger.warning(f"Invalid json: {music}")
                music = None
        if quiet:
            if "name" not in quiet:
                logger.warning(f"Invalid json: {quiet}")
                quiet = None
        if music:
            logger.debug(f"music: {music}")
            self.strips[sname].music = music
        if quiet:
            logger.debug(f"quiet: {quiet}")
            self.strips[sname].quiet = quiet
        await self.setPainter(sname)

    async def setPainter(self, sname):
        """Look at the HStrip for sname and decide what show it wants. Then
        Look in the shows to see if that one is running. If so, add it
        otherwise create and add it.
        This method takes into account the state of the music system so will
        switch from playing to quiet modes too.
        """
        striph = self.strips[sname]
        if self.music_playing:
            args = striph.music
            key = striph.music_h
        else:
            args = striph.quiet
            key = striph.quiet_h

        # We need to have been initialised
        if not (args and key):
            logger.debug("setPainter called but no args/key set")
            return

        try:
            newshow = self.shows[key]
            logger.debug("setPainter: Found that show")
        except KeyError:
            try:
                cls = args["name"]
                newshow = globals()[cls](self, args)
                self.shows[key] = newshow
                logger.debug("setPainter: Created that show")
            except KeyError:
                logger.debug("setPainter: Np painter class in args")
                return
            except NameError:
                logger.debug(f"setPainter: invalid painter class: {cls}")
                return

        if striph.current_show:
            logger.debug(f"setPainter: Leaving show {striph.current_show}")
            await striph.current_show.removeStrip(striph.ss)
            striph.current_show = None
        # Now everything has stopped we can set the global painter and args
        logger.debug("setPainter: Joining new show")
        newshow.addStrip(striph.ss)
        striph.current_show = newshow

        # self.controller.publish(f"strip/{self.name}/painter",
        #                         self.painter._as_payload())
    
    async def setBrightness(self, b):
        logger.debug(f"Setting brightness to {b}")
        self.strip.setBrightness(b)
        # Now run a frame of the strip show in case it's static
        self.strip.show()

    async def setState(self, s):
        state = s in ("ON", "on", "On", "True", "true", "1")
        logger.debug(f"Setting state ({s}) to {state}")
        self._state = state
        if state:
            for sname in self.strips.keys():
                await self.setPainter(sname)
        else:
            for show in self.shows.values():
                await show.stop()

    def publishState(self):
        """Publish our state
        """

        strips = {}
        for strip in self.strips.values():
            strip_data = {}
            strip_data["first_pixel"] = strip.first_pixel
            strip_data["pixels"] = strip.ss.numPixels()
            strip_data["painter"] = strip.quiet
            if strip.music:
                strip_data["music_painter"] = strip.music
            strips[strip.name] = strip_data



        payload = {
            "brightness": self.strip.getBrightness(),
            "state": "ON" if self._state else "OFF",
            "pixels": self.strip.numPixels(),
            "strips": strips
            }

        msg = json.dumps(payload, sort_keys=True).encode()
        logger.debug(f"Publish {msg}")

        self.mqctrl.publish(f"named/sensor/lamp/{self.name}", msg)

    def exit(self):
        for s in self.strips.values():
            s.ss.off()
