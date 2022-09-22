import time
import argparse
import colorsys
from rpi_ws281x import Color as Colour
from collections import deque
import itertools
import asyncio
import json
import logging
import numpy as np
import config
logger = logging.getLogger(__name__)


class StripShow:
    '''Define various ways to animate LEDs in a SubStrip.

    StripShow manages displaying pixels on a number of strips using an
    internal task.

    StripController has a collection of StripShows which it creates
    when needed.

    Strips are added to the show which causes the internal show() task
    to start. If all strips are removed the task is stopped.

    Whilst running the internal task runs show() which iterates over
    the current painter for each frame and then calls strip.show() to
    actually update the strip(s).

    The paint() method in the subclass updates the LED values and
    pauses as needed,

    Painters have access to the decoded message payload via the
    self.args attribute

    '''

    def __init__(self, controller, args):
        self.controller = controller
        self.strips = []
        self.name = self.__class__
        self.running = False
        self.args = None
        self.task = None
        self.args = args
        self.numPixels = 0
        self._gamma = np.load(config.GAMMA_TABLE_PATH)
        """Gamma lookup table used for nonlinear brightness correction"""


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
        if not self.running:
            self.start()
        return True

    async def removeStrip(self, strip):
        if strip in self.strips:
            self.strips.remove(strip)
        l = len(self.strips)
        logger.debug("%s has %d strips now", self.name, l)
        if not l:
            self.numPixels = 0
            logger.debug(f"{self.name} has no more strips - stopping")
            await self.stop()
            self.running = False
        return l

    def start(self):
        self.running = True
        self.task = asyncio.create_task(self.show())
        logger.debug(f"The show must go on. Let's {self.name} in {self.task.get_name()}")

    async def stop(self):
        """Stops the show"""
        logger.debug(f"{self.__class__.__name__} stop()")
        if not self.running:
            logger.debug(f"{self.__class__.__name__} already stopped/stopping")
            return
        self.running = False
        if self.task:
            try:
                # Allow the task to exit when self.running is set.
                await asyncio.wait_for(self.task, 0.1)
            except asyncio.TimeoutError:
                # OK, it's bad... the timeout cancelled it
                try:
                    # Wait for it to handle and respond to a cancel event
                    await self.task
                except asyncio.CancelledError:
                    # Or just accept it got hard-cancelled
                    logger.debug(f"The {self.name} show was hard cancelled")
        colour = Colour(0, 0, 0)
        for s in self.strips:
            s.off()
        await self.showHasFinished()
        logger.debug(f"The {self.name} show is over")

    async def show(self):
        logger.error(f"showing {self.name}")
        while True:
            if self.running:
                # paint frames.
                try:
                    # This may never finish
                    async for _frame in self.paint():
                        try:
                            # We assume there's only 1 actual strip
                            # which is split into subsstrips so we
                            # only need to render one strip. This may
                            # change if we have multiple real strips
                            self.strips[0].show()
                        except IndexError:
                            # We have had our strips removed !
                            if self.running:
                                logger.critical("No strips but still runnning???")
                            pass

                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.error(f"{e}", exc_info=True)
                    import traceback
                    logger.error(traceback.format_tb(e.__traceback__))
                    self.running = False
            else:
                await asyncio.sleep(0.1)

    async def showHasFinished(self):
        "Override this to do any cleanup after the show is done"
        pass

    def setPixelColor(self, p, c):
        for s in self.strips:
            s.setPixelColor(p, c)

    def hue_to_rgb(self, h):
        """Utility function for Painters. Converts a 0-255 hue into a
        Colour()"""
        return Colour(*(
            [int(c * 255) for c in colorsys.hsv_to_rgb(h/255, 1, 1)]))

    def prepare_for_strip(self, pixels):
        # Truncate values and cast to integer
        pixels = np.clip(pixels, 0, 255).astype(int)
        # Optional gamma correction
        # Note: is the p value here is related to p in the Effects class?
        if config.SOFTWARE_GAMMA_CORRECTION:
            p = self._gamma[pixels]
        else:
            p = pixels
        # Encode 24-bit LED values in 32 bit integers
        r = np.left_shift(p[0][:].astype(int), 8)
        g = np.left_shift(p[1][:].astype(int), 16)
        b = p[2][:].astype(int)
        return np.bitwise_or(np.bitwise_or(r, g), b)


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

class Sparkle(StripShow):
    """Sparkles"""

    async def paint(self):
        import random

        colour = self.args.get("colour",
                               #[255, 0, 0]  # Green
                               #[0, 255, 0]  # Red
                               #[0, 0, 255]  # Blue
                               "random"
                               #[255, 255, 255]
        )
        if colour == "random":
            colour = None
        else:
            colour = np.array(colour)/255
        # smoothness is the power of the slope used to fade in and out
        # if smoothness is zero the pixels appear suddenly and just
        # fade using decay.
        smoothness = self.args.get("smoothness", 1.0)
        # Decay is subtracted if smoothness == 0 otherwise it's a multiplier
        decay = self.args.get("decay", 0.01)
        delay = self.args.get("delay", 0)

        # make a 3xN array filled with 1.0
        sparkles = np.tile(0.0, (3, self.numPixels))
        logger.debug(f"Frame init {self.numPixels} {sparkles} ")
        while self.running:

            # Which pixel to glow
            pixel = random.randint(0, self.numPixels-1)
            val = sparkles[:, pixel]  # is it doing anything?
            if val[0] or val[1] or val[2]: # val.any() doesn't
                                           # short-circuit
                pass  # Pixel already lit
            else:
                if colour is not None:
                    sparkles[:, pixel] = colour
                else:
                    sparkles[:, pixel] = np.array([
                        random.random(),
                        random.random(),
                        random.random(),
                    ])

            if smoothness:
                # Convert from 0.0 -> 1.0 to 0.0 -> 1.0 -> 0.0
                pixels = (np.power(1 - np.fabs(sparkles + -0.5) * 2,
                                   smoothness)
                          * 255)
            else:
                pixels = sparkles * 255

            p = self.prepare_for_strip(pixels)
            self.setPixelColor(slice(0, len(p)), p)
            yield True

            # Now make the sparkles fade a bit for next time
            if smoothness:
                sparkles = np.fmax(sparkles - decay, 0.0)
            else:
                sparkles = sparkles * decay

            await asyncio.sleep(delay)
        logger.debug("%s: paint has finished", self.__class__.__name__)

    def visualize_sparkle(self, y):
        s = random.randrange(self.numPixels)
        # print(s)
        pixels *= 0.3

        pixels[0, s-1:s] = 255
        pixels[1, s-1:s] = 255
        pixels[2, s-1:s] = 255

        return pixels

    def visualize_sparkle_colour(self, y):
        s = random.randrange(self.numPixels)
        # print(s)
        pixels *= 0.8

        pixels[0, s-1:s] = random.randrange(255)
        pixels[1, s-1:s] = random.randrange(255)
        pixels[2, s-1:s] = random.randrange(255)

        return pixels
