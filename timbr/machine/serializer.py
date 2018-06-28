import six
import types
import base64
import os.path
import tempfile
import mimetypes
import simplejson as json
import numpy as np

if six.PY2:
    from cStringIO import StringIO
    import urllib2
    ADDINFOURL = urllib2.addinfourl
    import io
    StringIO = io.BytesIO
    INT_TYPES = (int, long)

if six.PY3:
    import io
    StringIO = io.BytesIO
    from urllib.request import addinfourl
    ADDINFOURL = addinfourl
    INT_TYPES = (int)
    long = int


def custom_encode(obj):
    if isinstance(obj, INT_TYPES):
        return {"__type__": "long",
                "__data__": str(obj)}
    elif isinstance(obj, ADDINFOURL):
        data = obj.read()
        return {"__type__": "file",
                "__name__": obj.geturl(),
                "__mime__": mimetypes.guess_type(obj.geturl()),
                "__data__": base64.b64encode(data)}
    elif isinstance(obj, types.FileType):
        data = obj.read()
        return {"__type__": "file",
                "__name__": obj.name,
                "__mime__": mimetypes.guess_type(obj.name),
                "__data__": base64.b64encode(data)}
    elif isinstance(obj, np.ndarray):
        data = StringIO()
        np.save(data, obj)
        return {"__type__": "ndarray",
                "__data__": base64.b64encode(data.getvalue()),
                "shape": obj.shape,
                "dtype": str(obj.dtype)}
    else:
        return obj

_encoder = json.JSONEncoder(default=custom_encode, encoding='utf-8')


def custom_decode(obj):
    try:
        if "__type__" in obj:
            if obj["__type__"] == "long":
                obj = long(obj["__data__"])
            elif obj["__type__"] == "ndarray":
                data = StringIO(base64.b64decode(obj["__data__"]))
                obj = np.load(data)
    except:
        # Fallback to raw structure
        pass
    finally:
        return obj


def wamp_custom_decode(obj):
    try:
        if "__type__" in obj and "__data__" in obj:
            del obj["__data__"]
    except:
        # Fallback to raw structure
        pass
    finally:
        return obj


_decoder = json.JSONDecoder(object_hook=custom_decode, encoding='utf-8')
_wamp_safe_decoder = json.JSONDecoder(object_hook=wamp_custom_decode, encoding='utf-8')

def dumps(obj):
    return _encoder.encode(obj)


def iterloads(msg, decoder=_decoder):
    offset = 0
    while(offset < len(msg)):
        chunk, offset = decoder.raw_decode(msg, idx=offset)
        yield chunk

def loads(msg, decoder=_decoder):
    output = [rec for rec in iterloads(msg, decoder=decoder)]
    if len(output) == 1:
        return output[0]
    elif len(output) == 0:
        return None
    else:
        return output

def wamp_safe_loads(msg):
    return loads(msg, decoder=_wamp_safe_decoder)
