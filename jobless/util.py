from hashlib import sha3_256

def calculate_checksum(content, hex=False):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    result = hash.digest()
    if hex:
        result = result.hex()
    return result

def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string"""
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        assert len(checksum) == 32, len(checksum)
        if as_bytes:
            return checksum
        else:
            return checksum.hex()
    
    if checksum is None:
        return
    raise TypeError(type(checksum))

class BufferInfo:
    __slots__ = (
        "checksum", "length", "is_utf8", "is_json", "json_type", 
        "is_json_numeric_array", "is_json_numeric_scalar",
        "is_numpy", "dtype", "shape", "is_seamless_mixed", 
        "str2text", "text2str", "binary2bytes", "bytes2binary",
        "binary2json", "json2binary"
    )
    def __init__(self, checksum, params:dict={}):
        for slot in self.__slots__:            
            setattr(self, slot, params.get(slot))
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        self.checksum = checksum
    
    def __setattr__(self, attr, value):
        if value is not None:                
            if attr == "length":
                if not isinstance(value, int):
                    raise TypeError(type(value))
                if not value >= 0:
                    raise ValueError
            if attr.startswith("is_"):
                if not isinstance(value, bool):
                    raise TypeError(type(value))
        if attr.find("2") > -1 and value is not None:
            if isinstance(value, bytes):
                value = value.hex()
        super().__setattr__(attr, value)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    def __getitem__(self, item):
        return getattr(self, item)

    def update(self, other):
        if not isinstance(other, BufferInfo):
            raise TypeError
        for attr in self.__slots__:
            v = getattr(other, attr)
            if v is not None:
                setattr(self, attr, v)
    
    def get(self, attr, default=None):
        value = getattr(self, attr)
        if value is None:
            return default
        else:
            return value
    
    def as_dict(self):
        result = {}
        for attr in self.__slots__:
            if attr == "checksum":
                continue
            v = getattr(self, attr)
            if v is not None:
                result[attr] = v
        return result
