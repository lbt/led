import asyncio
import os
import signal
import logging
import socket

from gmqtt import Client as MQTTClient
from gmqtt.mqtt.constants import MQTTv311

import logging
logger = logging.getLogger(__name__)


class LampController:
    def __init__(self, config):
        self.subscriptions = []
        self.handlers = []
        self.config = config
        self.host = socket.gethostname()
        self.cleanup_callbacks = set()
        self.mqtt = None

    async def setup_lamp(self):
        # Setup our sensors here so we can handle any exceptions in run()
        pass

    async def run(self):
        self.mqtt = MQTTClient(f"{socket.gethostname()}.{os.getpid()}")
        self.mqtt.set_auth_credentials(username=self.config["username"],
                                       password=self.config["password"])

        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message
        self.mqtt.on_disconnect = self.on_disconnect

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, self.ask_exit, stop_event)
        loop.add_signal_handler(signal.SIGTERM, self.ask_exit, stop_event)

        mqtt_host = self.config["mqtt_host"]
        mqtt_version = MQTTv311

        # Connect to the broker
        while not self.mqtt.is_connected:
            try:
                await self.mqtt.connect(mqtt_host, version=mqtt_version)
            except Exception as e:
                logger.warn(f"Error trying to connect: {e}. Retrying.")
                await asyncio.sleep(1)

        try:
            await self.setup_lamp()
        except Exception as e:
            logger.warning(f"Exception {e} thrown "
                           f"creating sensors",
                           exc_info=True)

        await stop_event.wait()  # This will wait until the client is signalled
        logger.debug(f"Stop received, cleaning up")
        for cb in self.cleanup_callbacks:
            await cb()  # Eg tells the probes to stop

        await self.mqtt.disconnect()  # Disconnect after any last messages sent
        logger.debug(f"client disconnected")

    def add_handler(self, handler):
        if handler not in self.handlers:
            self.handlers.append(handler)

    def on_message(self, client, topic, payload, qos, properties):
        tasks = list()
        for h in self.handlers:
            tasks.append(h(topic, payload))
        asyncio.gather(*tasks)

    def subscribe(self, topic):
        if topic not in self.subscriptions:
            self.subscriptions.append(topic)
            logger.debug(f"Subscribing to {topic}")
            if self.mqtt:
                self.mqtt.subscribe(topic)

    def on_connect(self, client, flags, rc, properties):
        for s in self.subscriptions:
            logger.debug(f"Re-subscribing to {s}")
            self.mqtt.subscribe(s)
        logger.debug('Connected and subscribed')

    def on_disconnect(self, client, packet, exc=None):
        logger.debug('Disconnected')

    def publish(self, topic, payload, retain=True):
        logger.debug(f"Publishing {topic} = {payload}")
        self.mqtt.publish(topic, payload, qos=2, retain=True)

    def ask_exit(self, stop_event):
        logger.warning("Client received signal and exiting")
        stop_event.set()

    def handle_exception(self, loop, context):
        # context["message"] will always be there; but context["exception"] may not
        msg = context.get("exception", context["message"])
        logger.error(f"Caught exception: {msg}", exc_info=True)

