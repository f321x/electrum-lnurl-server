from electrum.simple_config import SimpleConfig, ConfigVar

SimpleConfig.LNURL_SERVER_HOST = ConfigVar('plugins.lnurl_server.host', default='0.0.0.0', type_=str, plugin=__name__)
SimpleConfig.LNURL_SERVER_PORT = ConfigVar('plugins.lnurl_server.port', default=42321, type_=int, plugin=__name__)
SimpleConfig.LNURL_SERVER_DOMAIN = ConfigVar('plugins.lnurl_server.domain', default=None, type_=str, plugin=__name__)
