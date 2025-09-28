import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional
import ssl
import json

from electrum import util
from electrum.bip32 import BIP32Node, BIP32_PRIME
from electrum.lnutil import generate_keypair
from electrum.logging import Logger
from electrum.lrucache import LRUCache

import electrum_aionostr as aionostr
from electrum_aionostr.event import Event


if TYPE_CHECKING:
    from electrum.wallet import Abstract_Wallet
    from electrum.util import ProxyConnector


class NostrZapExtension(Logger):
    def __init__(self, wallet: 'Abstract_Wallet'):
        Logger.__init__(self)
        # maybe an ephemeral, random id would be sufficient?
        # Appendix F of NIP 57 is a bit unclear when the zap is validated by whom
        # so using a persistent, derived id might prevent some issues
        self.nostr_keypair = generate_keypair(
            BIP32Node.from_xkey(wallet.db.get('lightning_xprv')),
            key_family=int(999 | BIP32_PRIME)
        )
        self.network = wallet.network
        self.fallback_relays = wallet.config.NOSTR_RELAYS.split(',')
        self.ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=util.ca_path)
        self.zap_requests = LRUCache(maxsize=100)

    @asynccontextmanager
    async def _nostr_manager(self, relays: str):
        if self.network.proxy and self.network.proxy.enabled:
            proxy = util.make_aiohttp_proxy_connector(self.network.proxy, self.ssl_context)
        else:
            proxy: Optional['ProxyConnector'] = None
        manager_logger = self.logger.getChild('aionostr')
        manager_logger.setLevel("WARNING")
        async with aionostr.Manager(
                relays=relays,
                private_key=self.nostr_keypair.privkey.hex(),
                ssl_context=self.ssl_context,
                proxy=proxy,
                log=manager_logger
        ) as manager:
            yield manager

    @util.log_exceptions
    async def maybe_publish_zap_receipt(self, payment_hash: bytes, preimage: bytes):
        if (zap_request := self.zap_requests.get(payment_hash)) is None:
            return
        request_event_json, b11_invoice = zap_request
        assert isinstance(request_event_json, str)
        request_event = Event(**json.loads(request_event_json))
        tag_relays = next(iter(tag for tag in request_event.tags if tag[0] == 'relays'), None)
        relays = tag_relays[1:] if tag_relays and len(tag_relays) > 1 else self.fallback_relays
        tags = [
            ['bolt11', b11_invoice],
            ['description', request_event_json],
            ['preimage', preimage.hex()],
        ]
        if p_tag := next(iter(tag for tag in request_event.tags if tag[0] == 'p'), None):
            tags.append(p_tag)
        if e_tag := next(iter(tag for tag in request_event.tags if tag[0] == 'e'), None):
            tags.append(e_tag)
        if a_tag := next(iter(tag for tag in request_event.tags if tag[0] == 'a'), None):
            tags.append(a_tag)
        if P_tag := next(iter(tag for tag in request_event.tags if tag[0] == 'P'), None):
            tags.append(P_tag)
        if k_tag := next(iter(tag for tag in request_event.tags if tag[0] == 'k'), None):
            tags.append(k_tag)
        async with self._nostr_manager(relays) as manager:
            eid = await aionostr._add_event(
                manager,
                kind=9735,
                created_at=int(time.time()),
                content='',
                tags=tags,
                private_key=self.nostr_keypair.privkey.hex(),
            )
            self.logger.debug(f'Published zap receipt: {eid}')

    @staticmethod
    def validate_zap_request(zap_request_json: str, amount_query: int):
        event_dict = json.loads(zap_request_json)
        event = Event(**event_dict)
        assert event.verify(), "It MUST have a valid nostr signature"
        assert event.kind == 9734, f"Not a zap request: {event.kind=}"
        assert len(event.tags) > 0, "It MUST have tags"
        p_tags = [tag for tag in event.tags if len(tag) > 1 and tag[0] == 'p']
        assert len(p_tags) == 1, f"It MUST have only one p tag: {p_tags}"
        e_tags = [tag for tag in event.tags if len(tag) > 0 and tag[0] == 'e']
        assert 0 <= len(e_tags) <= 1, f"It MUST have 0 or 1 e tags: {e_tags}"
        amount_tag = [tag for tag in event.tags if len(tag) > 1 and tag[0] == 'amount']
        P_tags = [tag for tag in event.tags if len(tag) > 1 and tag[0] == 'P']
        if P_tags:
            assert len(P_tags) == 1, "There MUST be 0 or 1 P tags"
            assert P_tags[0][1] == event.pubkey, f"{p_tags=}: MUST be equal to the zap sender's pubkey"
        if amount_tag:
            assert len(amount_tag) == 1, f"multiple amount tags: {amount_tag}"
            assert int(amount_tag[1]) == amount_query, f"If there is an amount tag, \
            it MUST be equal to the amount query parameter: {amount_query=} != {amount_tag=}"
        # todo: how to validate this 'coordinate' properly?
        # If there is an a tag, it MUST be a valid NIP-33 event coordinate

    def store_zap_request(self, payment_hash: bytes, zap_request_json: str, b11_invoice: str):
        self.zap_requests[payment_hash] = (zap_request_json, b11_invoice)
