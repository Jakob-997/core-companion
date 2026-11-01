`verify.py` is included unchanged from Bitcoin Core v32.1:

https://github.com/bitcoin/bitcoin/blob/v32.1/contrib/verify-binaries/verify.py

SHA-256 of the upstream raw file: `f35fbf10740b86548e068fc689272cbbe5de012f86b8e4fea01103f7530d7409`

It is distributed under the MIT license in `COPYING`. Companion calls it with
a three-signature minimum and a temporary GPG keyring built from the eight
fingerprints pinned in `companion/core_download.py`. It does not use or change
the user's personal GPG keyring.
