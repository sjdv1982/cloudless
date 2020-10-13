from .file_transformer_plugin import FileTransformerPluginBase

class BashTransformerPlugin(FileTransformerPluginBase):
    REQUIRED_TRANSFORMER_PINS = ['bashcode', 'pins_']
    TRANSFORMER_CODE_CHECKSUMS = [
        # Seamless checksums for bash_transformer/executor.py
        '7cd387384084b210c57f346db6f352ac78f754c27df5a11bc2cd6a7384971eed', # Seamless 0.4
    ]
    def required_pin_handler(self, pin, transformation):
        assert pin in self.REQUIRED_TRANSFORMER_PINS
        if pin == "pins_":
            return True, False, None, None   # skip
        else:
            return False, True, False, False  # no skip, value-only, no JSON, no write-env
