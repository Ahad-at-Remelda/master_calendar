"""Settings module for white_label."""

import logging

from master_calendar.settings.base import *

logger = logging.getLogger(__name__)

try:
    from master_calendar.settings.local import *
except ModuleNotFoundError:
    logger.warning('Local settings file not initialized yet.')