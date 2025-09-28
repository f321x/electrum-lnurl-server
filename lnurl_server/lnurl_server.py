import asyncio
from typing import Optional
from typing import TYPE_CHECKING

from .server import LNURLServer

from electrum.plugin import BasePlugin, hook

if TYPE_CHECKING:
    from electrum.simple_config import SimpleConfig
    from electrum.daemon import Daemon
    from electrum.wallet import Abstract_Wallet


class LNURLServerPlugin(BasePlugin):

    def __init__(self, parent, config: 'SimpleConfig', name):
        BasePlugin.__init__(self, parent, config, name)
        self.config = config
        self.wallet = None  # type: Optional[Abstract_Wallet]
        self.server = None  # type: Optional[LNURLServer]

    @hook
    def daemon_wallet_loaded(self, daemon: 'Daemon', wallet: 'Abstract_Wallet'):
        # we use the first wallet loaded
        if self.server is not None:
            return
        self.wallet = wallet
        self.server = LNURLServer(self.config, wallet)
        asyncio.run_coroutine_threadsafe(self.server.run(), asyncio.get_running_loop())

    @hook
    def close_wallet(self, wallet: 'Abstract_Wallet'):
        if self.wallet != wallet:
            return
        if self.server:
            asyncio.run_coroutine_threadsafe(self.server.stop(), asyncio.get_running_loop())
            self.server = None
