from .file_transformer_plugin import FileTransformerPluginBase

class BashTransformerPlugin(FileTransformerPluginBase):
    REQUIRED_TRANSFORMER_PINS = ['bashcode', 'pins_']
    TRANSFORMER_CODE_CHECKSUMS = [
        # Seamless checksums for /seamless/graphs/bash_transformer/executor.py
        # Note that these are semantic checksums (invariant for whitespace),
        #  that are calculated from the Python AST rather than the source code text
        '7cd387384084b210c57f346db6f352ac78f754c27df5a11bc2cd6a7384971eed', # Seamless 0.4
        '5cdf7ba04b6faab840bbfc4460112b3c78d7d75124665c08ab8a80d5d2d4602f', # Seamless 0.4.1
        '54a3024fde08ac6526e31651730068482d61fb9d2cebb7a0bd18d455e7bbbeb6', # Seamless 0.6-devel
        '3eb91d8f14b22be1823cc54b4c888f00e1ad214bbda25bdc8de64b47051a499a', # Seamless 0.6
        '1cee47f07959d9a4899599a4ad230d3cd11058ab130666001d10d8fe8fbd842f', # Seamless 0.7
        '59e918e039a9b8a584ce9ba90b78941a8024ff9ff98db1133d67112974b0659f', # Seamless 0.8
    ]
    def required_pin_handler(self, pin, transformation):
        assert pin in self.REQUIRED_TRANSFORMER_PINS
        if pin == "pins_":
            return True, False, None, None   # skip
        else:
            return False, True, False, False  # no skip, json-value-only, no JSON, no write-env
