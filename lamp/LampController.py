import asyncio
import os
import signal
import logging
import socket

from gmqtt import Client as MQTTClient
from gmqtt.mqtt.constants import MQTTv311

from sensor2mqtt import MQController

import logging
logger = logging.getLogger(__name__)


class LampController(MQController):
    """Manages the Strips according to MQTT messages

    LampController sets up an MQTT connection and listens for MQTT
    messages.

    Topics can be subscribed to and callback handlers registered.

    It is stupid and calls all handlers for every message that is
    received which is OK when there are very few. Each handler should
    return ASAP after checking if the message is interesting.

    It also provides a publish mechanism.

    """

    async def setup_lamp(self):
        # Setup our sensors here so we can handle any exceptions in run()
        pass

    async def run(self):
        """This connects to the mqtt (retrying forever) and waits until
        :func:`ask_exit` is called at which point it exits cleanly.
        """
        await self.connect()

        try:
            await self.setup_lamp()
        except Exception as e:
            logger.warning(f"Exception {e} thrown "
                           f"creating {self.__class__}",
                           exc_info=True)

        await self.finish()  # This will wait until the client is signalled
