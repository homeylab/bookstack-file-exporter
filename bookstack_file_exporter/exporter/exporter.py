from bookstack_file_exporter.config_helper.config_helper import ConfigNode
import logging

log = logging.getLogger(__name__)

class BookNode():
    def __init__(self, config: ConfigNode):
        self._config = config