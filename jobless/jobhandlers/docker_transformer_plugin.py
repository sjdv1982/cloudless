from .file_transformer_plugin import FileTransformerPluginBase

class DockerTransformerPlugin(FileTransformerPluginBase):
    REQUIRED_TRANSFORMER_PINS = ['docker_command', 'docker_image', "docker_options", "pins_"]
    TRANSFORMER_CODE_CHECKSUMS = [
        # Seamless checksums for /seamless/graphs/docker_transformer/executor.py
        # Note that these are semantic checksums (invariant for whitespace),
        #  that are calculated from the Python AST rather than the source code text
        '2899b556035823fd911abfa9ab0948f19c8006e985919a4e1d249a9da2495bd9', # Seamless 0.4
        'a814c22fe71f58ec2ad5e59b31a480dc66ae185e3f708172eb8c5e20b6fd67eb', # Seamless 0.4.1
    ]

    def required_pin_handler(self, pin, transformation):
        assert pin in self.REQUIRED_TRANSFORMER_PINS
        if pin == "pins_":
            return True, False, None, None   # skip
        else:
            return False, True, False, False  # no skip, value-only, no JSON, no write-env
