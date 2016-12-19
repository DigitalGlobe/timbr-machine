from timbr.snapshot.snapshot import Snapshot
from timbr.machine import serializer
import numpy as np
import shapely
import tables
import json
import os
import sys
import json

from requests.compat import urljoin
import requests

from bson.objectid import ObjectId

import rasterio

from osgeo import gdal
gdal.UseExceptions()

def data_to_np(data):
    return np.fromstring(serializer.dumps(data), dtype="uint8")

class WrappedData(object):
    def __init__(self, snapshot, data, vrt_dir="/home/gremlin/vrt"):
        self.snapshot = snapshot
        self.data = data
        self.gid = data["id"]
        self._tmpfn = os.path.join(self.snapshot._vst_dir, ".tmp-{}.vrt".format(self.gid))

    def __repr__(self):
        return json.dumps(self.data)

    def __getitem__(self, item):
        return self.data[item]

    def fetch(self, base_url="http://idaho.timbr.io", node="TOAReflectance", level=0):
        relpath = "/".join([self.gid, node, str(level) + ".vrt"])
        url = urljoin(base_url, relpath)
        res = requests.get(url)
        if res.status_code != 200:
            res.raise_for_status()
        #write the vrt to a file
        with open(self._tmpfn, "w") as f:
            f.write(res.content)

    def _get_window(self):
        pass

    @property
    def vrt(self):
        pass

class DGSnapshot(Snapshot):
    def __init__(self, snapfile, vst_dir="/home/gremlin/.vst"):
        super(DGSnapshot, self).__init__(snapfile)
        self._vst_dir = vst_dir
        if not os.path.isdir(vst_dir):
            os.mkdir(vst_dir)

    def __getitem__(self, spec):
        if isinstance(spec, (int, long)):
            return WrappedData(self, self._input_fn(self._raw[spec].tostring()))
        elif spec in ("type", "bounds"):
            return self._input_fn(self.raw.attrs[spec].tostring())
        else:
            return list(self.__iter__(spec))

    def __iter__(self, spec=slice(None)):
        if isinstance(spec, slice):
            for rec in self._raw.iterrows(spec.start, spec.stop, spec.step):
                yield WrappedData(self, self._input_fn(rec.tostring()))
        else:
            for rec in self._raw[spec]:
                yield WrappedData(self, self._input_fn(rec.tostring()))

    @classmethod
    def from_geojson(cls, geojsonfile, snapfile=None, **kwargs):
        with open(geojsonfile) as f:
            geojson = json.load(f)
        if snapfile is None:
            fn = os.path.splitext(geojsonfile)[0]
            snapfile = fn + ".h5"
        elif os.path.splitext(snapfile)[-1] != ".h5":
            snapfile = snapfile + ".h5"
        snap = tables.open_file(snapfile, "w")
        raw = snap.create_vlarray(snap.root, "raw", atom=tables.UInt8Atom(shape=()), filters=tables.Filters(complevel=0))
        features = geojson["features"]
        for f in features:
            raw.append(data_to_np(f))
        raw.attrs.type = data_to_np({"type": geojson["type"]})
        raw.attrs.bounds = data_to_np({"bounds ": geojson["bounds"]})
        snap.close()
        return cls(snapfile, **kwargs)
