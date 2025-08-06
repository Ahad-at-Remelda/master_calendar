# scheduler_app/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
import logging

logger = logging.getLogger(__name__)

class CalendarConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_authenticated:
            self.group_name = f"user_{self.scope['user'].id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket CONNECTED for user {self.scope['user'].id} to group '{self.group_name}'")
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"WebSocket DISCONNECTED for user {self.scope['user'].id} from group '{self.group_name}'")

    async def calendar_update(self, event):
        """
        This is the event handler called by the channel layer.
        It forwards the message to the browser via WebSocket.
        """
        update_message = event.get("update", "calendar_changed")
        await self.send(text_data=json.dumps({
            'update': update_message
        }))
        logger.info(f"Sent WebSocket message '{update_message}' to group '{self.group_name}'")