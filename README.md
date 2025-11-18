## electrum-lnurl-server

Lightweight LNURL server plugin for the [Electrum Bitcoin Wallet](https://github.com/spesmilo/electrum)

#### Features

* [LNURL-pay (payRequest)](https://github.com/lnurl/luds/blob/luds/06.md)
* [Nostr Zaps (NIP-57)](https://github.com/nostr-protocol/nips/blob/master/57.md)

The plugin has no user management, it will accept payments for all given `domain.com/.well-known/lnurlp/{usernames}`.
The plugin can also be used as backend for a [Lightning Address](https://lightningaddress.com/).

#### Usage

##### Preparation
You need [run Electrum as daemon from source](https://github.com/spesmilo/electrum#running-from-targz) to be able to load the Plugin.
After installing Electrum from source check the [documentation](https://electrum.readthedocs.io/en/latest/cmdline.html#) for instructions on how to 
use it in **daemon** mode from the command line. 

###### TLDR

```bash
$ ./run_electrum daemon -d
$ ./run_electrum create -h
$ ./run_electrum load_wallet
$ ./run_electrum getunusedaddress
$ ./run_electrum open_channel -h
$ ./run_electrum get_submarine_swap_providers -h
$ ./run_electrum reverse_swap -h
$ ./run_electrum stop
```

Now you should have a fresh running instance of Electrum with a open lightning channel and incoming liquidity.
For an easier initial setup procedure you can also initialize the wallet in GUI mode instead of using the commands above.

##### Installing the Plugin

1. Clone this repository
```bash
$ git clone https://github.com/f321x/electrum-lnurl-server
```

2. Symlink the `lnurl_server` directory into the `electrum/electrum/plugins/.` directory
```bash
$ ln -s /absolute/path/to/electrum-lnurl-server/lnurl_server /absolute/path/to/electrum/electrum/plugins/lnurl_server
```

3. Enable the Plugin in Electrum
```bash
$ ./run_electrum setconfig -o plugins.lnurl_server.enabled true
```

4. Configure the domain on which your server will receive requests
```bash
$ ./run_electrum setconfig -o plugins.lnurl_server.domain 'example.lightningaddress.com'
```

5. (Optional) Configure the listening port (default is 42321)
```bash
$ ./run_electrum setconfig -o plugins.lnurl_server.port 8080
```

Find all available config options [here](https://github.com/f321x/electrum-lnurl-server/blob/master/lnurl_server/__init__.py).

Now you can start the **daemon** again and Electrum will accept incoming payments.
To test the plugin is working correctly you can run this on the same machine:
```bash
$ curl localhost:42321/.well-known/lnurlp/any-name
```

##### Support

If you find this plugin useful feel free to push some sats to `x@lnaddress.com`.
