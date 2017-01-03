from timbr.snapshot.snapshot import Snapshot
from timbr.machine import serializer
import numpy as np
import tables
import h5py
import json
import os
import sys
import json
import inspect

from requests.compat import urljoin
import requests

import xml.etree.cElementTree as ET
import rasterio

from osgeo import gdal
gdal.UseExceptions()

def data_to_np(data):
    return np.fromstring(serializer.dumps(data), dtype="uint8")

def parse_bounds(raw):
    bounds = [float(n.strip()) for n in raw.split(",")]
    return bounds

def index_to_slice(ind, rowstep, colstep):
    i, j = ind
    window = ((i * rowstep, (i + 1) * rowstep), (j * colstep, (j + 1) * colstep))
    return window

def roi_from_bbox_projection(src, user_bounds, preserve_blocksize=True):
    roi = src.window(*user_bounds)
    if not preserve_blocksize:
        return roi
    blocksafe_roi = rasterio.windows.round_window_to_full_blocks(roi, src.block_shapes)
    return blocksafe_roi

def generate_blocks(window, blocksize):
    rowsize, colsize = blocksize
    nrowblocks = window.num_rows / rowsize
    ncolblocks = window.num_cols / colsize
    for ind in np.ndindex((nrowblocks, ncolblocks)):
        yield index_to_slice(ind, nrowblocks, ncolblocks)

def build_url(gid, base_url="http://idaho.timbr.io", node="TOAReflectance", level=0):
    relpath = "/".join([gid, node, str(level) + ".vrt"])
    return urljoin(base_url, relpath)

class MetaWrap(type):
    def __call__(cls, *args, **kwargs):
        if "data" in kwargs and kwargs["data"] is not None:
            for name, attr in inspect.getmembers(kwargs["data"]):
                if name not in dir(cls):
                    setattr(cls, name, attr)
        return type.__call__(cls, *args, **kwargs)

class WrappedGeoJSON(object):
    __metaclass__ = MetaWrap
    def __init__(self, snapshot, data=None, vrt_dir="/home/gremlin/project/vrt"):
        self._snapshot = snapshot
        self._data = data
        self._gid = data["id"]
        self._vrt_dir = vrt_dir
        self._vrt_file = os.path.join(self._vrt_dir, "{}.vrt".format(self._gid))

    def __setitem__(self, key, value):
        raise NotSupportedError

    def __delitem__(self, key):
        raise NotSupportedError

    def fetch(self, **kwargs):
        url = build_url(self._gid, **kwargs)
        self._user_bounds = parse_bounds(self._snapshot["bounds"]["bounds"])
        self._src = rasterio.open(url)
        self._roi = roi_from_bbox_projection(self._src, self._user_bounds)

        self._snapshot._fileh.close():
        h = h5py.File(self._snapshot._filename)
        self._dpath = os.path.join("image_data", self._gid)
        ds = h.create_dataset(self._dpath, (len(self._src.indexes), self._roi.num_rows, self._roi.num_cols), self._src.meta.get("dtype", "float32"))
        read_window = ((self._roi.row_off, self._roi.num_rows), (self._roi.col_off, self._roi.num_cols))
        arr = self._src.read(window=read_window)
        ds[:,:,:] = arr
        h.flush()
        h.close()

        self._snapshot._fileh = tables.open(self.snapshot._filename) #reopen snapfile w pytables
        self._generate_vrt()
        self._src.close()
        return self._vrt_file

    def _generate_vrt(self):
        vrt = ET.Element("VRTDataset", {"rasterXsize": str(self._roi.num_cols),
                        "rasterYSize": str(self._roi.num_rows)})
        ET.SubElement(vrt, "SRS").text = str(self._src.crs['init']).upper()
        ET.SubElement(vrt, "GeoTransform").text = ", ".join([str(c) for c in self._src.get_transform()])
        for i in self._src.indexes:
            band = ET.SubElement(vrt, "VRTRasterBand", {"dataType": self._src.dtypes[i-1].title(), "band": str(i)})
            src = ET.SubElement(band, "SimpleSource")
            ET.SubElement(src, "SourceFilename").text = "HDF5:{}://image_data/{}".format(self._snapshot._filename, self._gid)
            ET.SubElement(src, "SourceBand").text =str(i)
            ET.SubElement(src, "SrcRect", {"xOff": "0", "yOff": "0",
                                           "xSize": str(self._roi.num_cols), "ySize": str(self._roi.num_rows)})
            ET.SubElement(src, "DstRect", {"xOff": "0", "yOff": "0",
                                           "xSize": str(self._roi.num_cols), "ySize": str(self._roi.num_rows)})

            ET.SubElement(src, "SourceProperties", {"RasterXSize": str(self._roi.num_cols), "RasterYSize": str(self._roi.num_rows),
                                                    "BlockXSize": "128", "BlockYSize": "128", "DataType": self._src.dtypes[i-1].title()})
        vrt_str = ET.tostring(vrt)
        self._vrt_file = os.path.join(self._vrt_dir, "{}.vrt".format(self._gid))
        with open(self._vrt_file, "w") as f:
            f.write(vrt_str)

    @property
    def vrt(self):
        if os.path.exists(self._vrt_file):
            return self._vrt_file
        print("fetching image from vrt, writing to snapshot file and generating vrt reference")
        return self.fetch()

class DGSnapshot(Snapshot):
    def __init__(self, snapfile, vst_dir="/home/gremlin/project/.vst"):
        super(DGSnapshot, self).__init__(snapfile)
        self._vst_dir = vst_dir
        if not os.path.isdir(vst_dir):
            os.mkdir(vst_dir)
        self._lut = {}

    def __getitem__(self, spec):
        if isinstance(spec, (int, long)):
            return self._wrap_data(self._input_fn(self._raw[spec].tostring()))
        elif spec in ("type", "bounds"):
            return self._input_fn(self.raw.attrs[spec].tostring())
        else:
            return list(self.__iter__(spec))

    def __iter__(self, specs=slice(None)):
        if isinstance(spec, slice):
            for rec in self._raw.iterrows(spec.start, spec.stop, spec.step):
                yield self._wrap_data(self._input_fn(rec.tostring()))
        else:
            for rec in self._raw[spec]:
                yield self._wrap_data(self._input_fn(rec.tostring()))

    def _wrap_data(self, data):
        if data["id"] not in self._lut:
            self._lut[data["id"]] = WrappedGeoJSON(self, data=data)
        return self._lut[data["id"]]

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
        raw.attrs.bounds = data_to_np({"bounds": geojson["bounds"]})
        snap.close()
        return cls(snapfile, **kwargs)
