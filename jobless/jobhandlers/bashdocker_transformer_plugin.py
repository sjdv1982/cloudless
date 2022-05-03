from .file_transformer_plugin import FileTransformerPluginBase

class BashDockerTransformerPlugin(FileTransformerPluginBase):
    REQUIRED_TRANSFORMER_PINS = [('bashcode', 'docker_command'), 'pins_']
    TRANSFORMER_CODE_CHECKSUMS = [
        # Seamless checksums for /seamless/graphs/docker_transformer/executor.py
        # Note that these are semantic checksums (invariant for whitespace),
        #  that are calculated from the Python AST rather than the source code text
        #'2899b556035823fd911abfa9ab0948f19c8006e985919a4e1d249a9da2495bd9', # Seamless 0.4
        #'a814c22fe71f58ec2ad5e59b31a480dc66ae185e3f708172eb8c5e20b6fd67eb', # Seamless 0.4.1
        #'c67306290a03743107019eb883582e4fa53e544d1485e7a4de404ea918476557', # Seamless 0.5
        #'38c1d48e4981d977570ad9f0107128bcf7a0f7cadfee0f84fe9cda3290751874', # Seamless 0.6-devel
        #'7ca0196fef59b9d7e02d8334eb77b43a3d44cdf4a8a1c9bc1876d66fc7af94d5', # Seamless 0.6

        'c2c1a13ba4a68004eaeb9b5300473c1b39ebfc6dff922ad1893fe67b9668c80d', # Seamless 0.7
        '1cee47f07959d9a4899599a4ad230d3cd11058ab130666001d10d8fe8fbd842f', # Seamless 0.7 in rpbs/seamless
        'bdbeaaa209a9ee303c03efb280e66684a68093c1b9f925fa3b7e0114cbe87591', # Seamless 0.8
        '59e918e039a9b8a584ce9ba90b78941a8024ff9ff98db1133d67112974b0659f', # Seamless 0.8 bash transformer
    ]

    def allowed_docker_image(self, docker_image):
        return True

    def allowed_powers(self, powers):
        return powers is None or len(powers) == 0 or list(powers) == ["docker"]

    def required_pin_handler(self, pin, transformation):
        if pin == "pins_":
            return True, False, None, None   # skip
        else:
            return False, True, False, False  # no skip, json-value-only, no JSON, no write-env
