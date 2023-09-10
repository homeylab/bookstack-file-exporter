from bookstack_file_exporter.config_helper.config_helper import ConfigNode

class PageExporter():
    def __init__(self, config: ConfigNode):
        self._config = config