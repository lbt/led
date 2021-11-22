import time
import argparse
import colorsys
from rpi_ws281x import Color as Colour
from collections import deque
import itertools
import asyncio
import json
import logging
logger = logging.getLogger(__name__)


class StripShow:
    '''Define various ways to animate LEDs in a SubStrip.

    StripShow manages an internal task which runs show() forever.

    show() calls the current painter on each iteration and then calls
    strip.show() to actually update the strip.

    The painter updates the LED values and pauses as needed,

    Painters have access to the decoded message payload via the
    self.args attribute

    '''


    def __init__(self, controller, args):
        self.controller = controller
        self.strips = []
        self.name = self.__class__
        #self.painter = self.Painter({"painter": "rainbowChase"})
        self.running = True
        self.args = None
        self.task = None
        self.args = args
        self.numPixels = 0

    def _as_payload(self):
        return json.dumps(self.args, separators=(',', ':')).encode("utf-8")

    def addStrip(self, strip):
        if strip in self.strips:
            return
        for s in self.strips:
            if s.numPixels() != strip.numPixels():
                logger.warning(f"""Tried to add {strip} which has {strip.numPixels()}
                pixels but existing strip(s) have {s.numPixels} pixels""")
                return False
        self.strips.append(strip)
        self.numPixels = strip.numPixels()
        logger.debug(f"{self.name} has {self.numPixels} pixels")
        return True

    async def removeStrip(self, strip):
        if strip in self.strips:
            self.strips.remove(strip)
        l = len(self.strips)
        if not l:
            self.numPixels = 0
            logger.debug(f"{self.name} has no more strips - stopping")
            await self.stop()
        return l

    def start(self):
        self.task = asyncio.create_task(self.show())
        self.running = True
        logger.debug(f"The show must go on. Let's {self.name}")

    async def stop(self):
        """Stops the show"""
        logger.debug(f"stop()")
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            logger.debug(f"The {self.name} show is over")

    async def show(self):
        logger.error(f"showing {self.name}")
        while True:
            if self.running:
                # paint a frame
                async for _frame in self.paint():
                    # We only need to render one strip
                    self.strips[0].show()
            else:
                await asyncio.sleep(0.1)

    def setPixelColor(self, p, c):
        for s in self.strips:
            s.setPixelColor(p, c)

    def hue_to_rgb(self, h):
        """Utility function for Painters. Converts a 0-255 hue into a
        Colour()"""
        return Colour(*(
            [int(c * 255) for c in colorsys.hsv_to_rgb(h/255, 1, 1)]))


################################################################
# Painter Classes
class RainbowFade(StripShow):
    async def paint(self):
        """Fade through all the colours of a Rainbow"""
        try:
            speed = self.args.get("speed", 10)
        except Exception as e:
            logger.error(f"Error handling rainbowFade args: {e}")
            self.running = False
            return
        while True:
            t = time.time() * speed
            colour = self.hue_to_rgb(t % 255)
            for i in range(self.numPixels):
                self.setPixelColor(i, colour)
            yield True
            await asyncio.sleep(1/60)


class SolidColour(StripShow):
    async def paint(self):
        """Set the entire display to a colour."""
        try:
            colour = Colour(*self.args["colour"])
        except (KeyError, AttributeError):
            colour = Colour(255, 0, 0)
        for i in range(self.numPixels):
            self.setPixelColor(i, colour)
        # No need to run again
        self.running = False
        yield True


class SolidColourWipe(StripShow):
    async def paint(self):
        """Wipe colour across display a pixel at a time."""
        wait_ms = self.args.get("wait_ms", 50)
        try:
            colour = Colour(*self.args["colour"])
        except (KeyError, AttributeError):
            colour = Colour(255, 0, 0)
        for i in range(self.numPixels):
            self.setPixelColor(i, colour)
            yield True
            await asyncio.sleep(wait_ms/1000.0)
        self.running = False


class TheaterChase(StripShow):
    async def paint(self):
        """Movie theater light style chaser animation."""
        try:
            reverse = self.args.get("reverse", False)
            line = self.args.get("line_length", 8)
            wait_ms = self.args.get("wait_ms", 50)
            colour = Colour(*self.args.get("colour", (255, 0, 0)))
        except Exception as e:
            logger.error(f"Error handling theaterChase args: {e}")
            self.running = False
            return
        num = self.numPixels
        reverse = -1 if reverse else 1
        while True:
            for q in range(line):
                for i in range(0, num, line):
                    self.setPixelColor((i+(q*reverse)) % num, colour)
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, num, line):
                    self.setPixelColor((i+(q*reverse)) % num, 0)



class TheaterChaseRainbow(StripShow):
    async def paint(self):
        """Rainbow movie theater light style chaser animation."""
        try:
            reverse = self.args.get("reverse", False)
            line = self.args.get("line_length", 4)
            wait_ms = self.args.get("wait_ms", 50)
        except Exception as e:
            logger.error(f"Error handling theaterChaseRainbow args: {e}")
            self.running = False
            return
        num = self.numPixels
        logger.error(f"Pixels {num} {num}")
        reverse = -1 if reverse else 1
        j = 0
        while True:
            for q in range(line):
                for i in range(0, num, line):
                    self.setPixelColor((i+(q*reverse)) % num,
                                       self.hue_to_rgb((i+j) % 255))
                yield True
                await asyncio.sleep(wait_ms/1000.0)
                for i in range(0, num, line):
                    self.setPixelColor((i+(q*reverse)) % num, 0)
            j = (j+1) % 256


class RainbowChase(StripShow):
    async def paint(self):
        """Draw rainbow that uniformly distributes itself across all pixels."""
        try:
            reverse = self.args.get("reverse", False)
            speed = self.args.get("speed", 10)
        except Exception as e:
            logger.error(f"Error handling rainbowChase args: {e}")
            self.running = False
            return
        n = self.numPixels
        reverse = -1 if reverse else 1
        while True:
            t = time.time() * speed
            for i in range(n):
                # Spread the Hue range over the pixels & also cycle it
                # over time
                h = (i / n) * 255  # scale to 0-255
                self.setPixelColor(i, self.hue_to_rgb((t + h * reverse) % 255))
            await asyncio.sleep(1/60)
            yield True
