import hashlib
import json
from typing import Dict, Any

class StripState:
    """Helper class that encapsulates the Strip state
    """

    def __init__(self, name, strip, config):
        self.name = name
        self.strip = strip
        self.first_pixel = config[name]["first_pixel"]
        self.num_pixels = config[name]["num_pixels"]
        self.ss = strip.createPixelSubStrip(self.first_pixel,
                                            num=self.num_pixels)
        # We store the config and hash of each config
        self._quiet = None
        self.quiet_h = None
        self._music = None
        self.music_h = None
        self.current_show = None

    @property
    def quiet(self):
        return self._quiet

    @quiet.setter
    def quiet(self, val):
        assert val is not None
        self._quiet = val
        self.quiet_h = self.dict_hash(val)

    @property
    def music(self):
        return self._music

    @music.setter
    def music(self, val):
        self._music = val
        if val is not None:
            self.music_h = self.dict_hash(val)
        else:
            self.music_h = None

    # https://www.doc.ic.ac.uk/~nuric/coding/how-to-hash-a-dictionary-in-python.html
    def dict_hash(self, dictionary: Dict[str, Any]) -> str:
        """MD5 hash of a dictionary."""
        dhash = hashlib.md5()
        # We need to sort arguments so {'a': 1, 'b': 2} is
        # the same as {'b': 2, 'a': 1}
        encoded = json.dumps(dictionary, sort_keys=True).encode()
        dhash.update(encoded)
        return dhash.hexdigest()
