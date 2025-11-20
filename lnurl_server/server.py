import asyncio
import json
from typing import Optional
from typing import TYPE_CHECKING
from secrets import token_hex

from . import util
from .nostr_zaps import NostrZapExtension

from electrum.lrucache import LRUCache
from electrum.util import log_exceptions, ignore_exceptions, EventListener, event_listener
from electrum.logging import Logger
from electrum.lnaddr import lnencode
from electrum.invoices import PR_PAID

from aiohttp import web
import aiohttp

if TYPE_CHECKING:
    from electrum.simple_config import SimpleConfig
    from electrum.wallet import Abstract_Wallet
    from electrum.invoices import Request


class LNURLServer(Logger, EventListener):
    """
    public API:
    - /.well-known/lnurlp/{any_username}
    - /lnurlp/callback/{token}
    """
    MIN_RECEIVE_AMOUNT_MSAT = 1000

    def __init__(self, config: 'SimpleConfig', wallet: 'Abstract_Wallet'):
        Logger.__init__(self)
        self.config = config
        self.wallet = wallet
        self.server = None  # type: Optional[web.TCPSite]
        self.domain: str = util.normalize_url(self.config.LNURL_SERVER_DOMAIN)
        self.listen_host: str = self.config.LNURL_SERVER_HOST
        self.port: int = self.config.LNURL_SERVER_PORT
        self.callbacks = LRUCache(maxsize=10_000)
        self.zap_manager = NostrZapExtension(self.wallet)
        self.register_callbacks()
        self.addrequest_url = self.get_addrequest_endpoint()
        self.logger.info(f'addrequest url {self.addrequest_url}')

    def get_addrequest_endpoint(self):
        url = self.config.LNURL_SERVER_ADDREQUEST_ENDPOINT
        if url is None:
            url = 'http://localhost:%d/api/add_request' % self.config.LNURL_SERVER_PORT
        return url

    @ignore_exceptions
    @log_exceptions
    async def run(self):

        while self.wallet.has_password() and self.wallet.get_unlocked_password() is None:
            self.logger.warning("This wallet is password-protected. Please unlock it to start the lnurl server plugin")
            await asyncio.sleep(10)

        while not self.wallet.has_lightning():
            self.logger.warning("LNURL server needs a wallet with lightning")
            await asyncio.sleep(10)

        app = web.Application()
        app.add_routes([web.get('/.well-known/lnurlp/{username}', self.lnurl_pay)])
        app.add_routes([web.get('/lnurlp/callback/{token}', self.lnurlp_callback)])
        app.add_routes([web.post('/api/add_request', self.add_request)])

        runner = web.AppRunner(app)
        await runner.setup()
        self.server = web.TCPSite(runner, host=self.listen_host, port=self.port)
        await self.server.start()
        self.logger.info(f"running and listening on port {self.port}")

    async def stop(self):
        if self.server is not None:
            await self.server.stop()
        self.server = None
        self.unregister_callbacks()

    async def lnurl_pay(self, r):
        username = r.match_info['username']
        if not isinstance(username, str) or len(username) > 100:
            raise web.HTTPBadRequest(reason='Invalid username')
        # handle requests for all usernames, would there be a point in rejecting non-registered usernames?
        self.logger.info(f"lnurlp request for {username=}")
        max_sendable_msat = int(self.wallet.lnworker.num_sats_can_receive()) * 1000
        if max_sendable_msat < self.MIN_RECEIVE_AMOUNT_MSAT:
            error = {"status": "ERROR", "reason": "cannot receive anything, no liquidity."}
            return web.json_response(error)
        callback_token = token_hex(16)
        metadata = json.dumps([['text/plain', f'Payment to {username}']])
        self.callbacks[callback_token] = metadata
        assert max_sendable_msat >= self.MIN_RECEIVE_AMOUNT_MSAT
        response = {
            'callback': f"https://{self.domain}/lnurlp/callback/{callback_token}",
            'maxSendable': max_sendable_msat,
            'minSendable': self.MIN_RECEIVE_AMOUNT_MSAT,
            'metadata': metadata,
            'commentAllowed': 50,
            'tag': 'payRequest',
            'allowsNostr': True,
            'nostrPubkey': self.zap_manager.nostr_keypair.pubkey.hex(),
        }
        return web.json_response(response)

    async def lnurlp_callback(self, r):
        token = r.match_info['token']
        metadata = self.callbacks.get(token)
        if metadata is None:
            error = {"status":"ERROR", "reason":"request not found, maybe expired, try again."}
            return web.json_response(error)

        amount_msats = int(r.query['amount'])
        if amount_msats // 1000 > int(self.wallet.lnworker.num_sats_can_receive()):
            error = {"status": "ERROR", "reason": "cannot receive this amount, try smaller payment."}
            return web.json_response(error)
        if amount_msats < self.MIN_RECEIVE_AMOUNT_MSAT:
            error = {"status": "ERROR", "reason": "amount below minSendable."}
            return web.json_response(error)

        if (zap_request := r.query.get('nostr')) is not None:
            try:
                zapped_event_id = self.zap_manager.validate_zap_request(zap_request, amount_msats)
            except Exception as e:
                self.logger.debug(f"invalid {zap_request=}: ", exc_info=True)
                error = {"status": "ERROR", "reason": f"Invalid zap request: {str(e)}."}
                return web.json_response(error)
        else:
            zapped_event_id = None

        async with aiohttp.ClientSession() as session:
            metadata = zap_request or metadata  # prioritize zap_request over metadata
            comment = r.query.get('comment', 'lnurlp request')[:50]
            req = {
                'amount_msats': amount_msats,
                'comment': comment,
                'metadata': metadata,
                'event_id': zapped_event_id,
            }
            async with session.post(self.addrequest_url, json=req) as response:
                r = await response.json()

        b11 = r['invoice']
        payment_hash = bytes.fromhex(r['rhash'])

        if zap_request:
            self.zap_manager.store_zap_request(payment_hash, zap_request, b11)
        response = {
            'pr': b11,
            'routes': [],
        }
        return web.json_response(response)

    async def add_request(self, r):
        params = await r.json()
        try:
            amount_msats = int(params['amount_msats'])
            comment = params['comment']
            metadata = params['metadata']
        except Exception as e:
            self.logger.info(f"{r}, {params}, {e}")
            raise web.HTTPUnsupportedMediaType()
        pay_req_key = self.wallet.create_request(
            amount_sat=amount_msats // 1000,
            message=comment,
            exp_delay=120,
            address=None,
        )
        pay_req = self.wallet.get_request(pay_req_key)
        payment_info = self.wallet.lnworker.get_payment_info(pay_req.payment_hash)
        assert payment_info
        lnaddr, _invoice = self.wallet.lnworker.get_bolt11_invoice(
            payment_info=payment_info,
            message='',  # will get replaced below with hash
            fallback_address=None,
        )
        lnaddr.tags = [tag for tag in lnaddr.tags if tag[0] != 'd']
        lnaddr.tags.append(['h', metadata])
        b11 = lnencode(lnaddr, self.wallet.lnworker.node_keypair.privkey)
        response = {
            'invoice': b11,
            'rhash': pay_req.payment_hash.hex()
        }
        return web.json_response(response)

    @event_listener
    async def on_event_request_status(self, wallet: 'Abstract_Wallet', key: str, status):
        if wallet != self.wallet:
            return
        request: Optional['Request'] = self.wallet.get_request(key)
        preimage = self.wallet.lnworker.get_preimage(request.payment_hash)
        if not request or not request.is_lightning():
            return
        if status != PR_PAID or not preimage:
            return
        try:
            await self.zap_manager.maybe_publish_zap_receipt(request.payment_hash, preimage)
        except Exception:
            self.logger.exception(f'failed to broadcast zap confirmation event')
