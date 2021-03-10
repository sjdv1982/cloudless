from .file_transformer_plugin import FileTransformerPluginBase

class BashTransformerPlugin(FileTransformerPluginBase):
    REQUIRED_TRANSFORMER_PINS = ['bashcode', 'pins_']
    TRANSFORMER_CODE_CHECKSUMS = [
        # Seamless checksums for /seamless/graphs/bash_transformer/executor.py
        # Note that these are semantic checksums (invariant for whitespace),
        #  that are calculated from the Python AST rather than the source code text
        '7cd387384084b210c57f346db6f352ac78f754c27df5a11bc2cd6a7384971eed', # Seamless 0.4
        '5cdf7ba04b6faab840bbfc4460112b3c78d7d75124665c08ab8a80d5d2d4602f', # Seamless 0.4.1
    ]
    def required_pin_handler(self, pin, transformation):
        assert pin in self.REQUIRED_TRANSFORMER_PINS
        if pin == "pins_":
            return True, False, None, None   # skip
        else:
            return False, True, False, False  # no skip, json-value-only, no JSON, no write-env
