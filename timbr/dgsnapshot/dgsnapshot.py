from timbr.snapshot.snapshot import Snapshot
from timbr.machine import serializer

import tables
import h5py

import os
import sys
import json
import inspect
from functools import partial
from collections import defaultdict
from itertools import groupby
import threading

import requests
from requests.compat import urljoin
import xml.etree.cElementTree as ET
import pycurl

import rasterio
from rasterio.io import MemoryFile
import dask
from dask.delayed import delayed
import dask.array as da
import numpy as np

from osgeo import gdal
gdal.UseExceptions()

_curl_pool = defaultdict(pycurl.Curl)

threaded_get = partial(dask.threaded.get, num_workers=8)
dask.set_options(get=threaded_get)

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

def build_url(gid, base_url="http://idaho.timbr.io", node="TOAReflectance", level="0"):
    relpath = "/".join([gid, node, str(level) + ".vrt"])
    return urljoin(base_url, relpath)

def collect_urls(vrt):
    doc = ET.parse(vrt)
    urls = list(set(item.text for item in doc.getroot().iter("SourceFilename") 
                if item.text.startswith("http://")))
    chunks = []
    for url in urls:
        head, _ = os.path.splitext(url)
        head, y = os.path.split(head)
        head, x = os.path.split(head)
        head, key = os.path.split(head)
        y = int(y)
        x = int(x)
        chunks.append((x, y, url))

    grid = [[rec[-1] for rec in sorted(it, key=lambda x: x[1])]
            for key, it in groupby(sorted(chunks, key=lambda x: x[0]), lambda x: x[0])]
    return grid

@delayed
def load_url(url):
    thread_id = threading.current_thread().ident
    _curl = _curl_pool[thread_id]
    finished = False
    while not finished:
        with MemoryFile() as memfile:
            _curl.setopt(_curl.URL, url)
            _curl.setopt(_curl.WRITEDATA, memfile)
            _curl.perform()
            try:
                with memfile.open(driver="GTiff") as dataset:
                    arr = dataset.read()
                    finished = True
            except rasterio.RasterioIOError:
                print("Errored on {}".format(url))
                arr = np.zeros([8,256,256], dtype=np.float32)
    return arr

def pfetch(vrt):
    buf = da.concatenate(
        [da.concatenate([da.from_delayed(load_url(url), shape=(8,256,256)) for url in row], 
                        axis=1) for row in collect_urls(vrt)], axis=2)
    # NOTE: next line will execute
    wat = buf.compute()
    return wat

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

    def __setitem__(self, key, value):
        raise NotSupportedError

    def __delitem__(self, key):
        raise NotSupportedError

    def fetch(self, node="TOAReflectance", level="0"):
        user_bounds = parse_bounds(self._snapshot["bounds"]["bounds"])
        url = build_url(self._gid, node=node, level=level)
        self._src = rasterio.open(url)
        self._roi = roi_from_bbox_projection(self._src, user_bounds)
        #self._new_bounds = self._src.window_bounds(self._roi)

        res = requests.get(url, params={"window": ",".join([str(c) for c in self._roi.flatten()])})
        tmp_vrt = os.path.join(self._vrt_dir, ".".join([".tmp", node, level, self._gid + ".vrt"]))
        with open(tmp_vrt, "w") as f:
            f.write(res.content)

        print("Starting parallel fetching...")
        image = pfetch(tmp_vrt)
        print("Fetch complete")

        self._snapshot._fileh.close()
        h = h5py.File(self._snapshot._filename)
        self._dpath = os.path.join("image_data", self._gid, node, level)
        ds = h.create_dataset(self._dpath, image.shape, self._src.meta.get("dtype", "float32"))
        ds[:,:,:] = image
        h.flush()
        h.close()

        self._snapshot._fileh = tables.open_file(self._snapshot._filename) #reopen snapfile w pytables
        vrt_file = self._generate_vrt(node=node, level=level)
        self._src.close()
        return vrt_file

    def _generate_vrt(self, node="TOAReflectance", level="0"):
        vrt = ET.Element("VRTDataset", {"rasterXsize": str(self._roi.num_cols),
                        "rasterYSize": str(self._roi.num_rows)})
        ET.SubElement(vrt, "SRS").text = str(self._src.crs['init']).upper()
        ET.SubElement(vrt, "GeoTransform").text = ", ".join([str(c) for c in self._src.get_transform()])
        for i in self._src.indexes:
            band = ET.SubElement(vrt, "VRTRasterBand", {"dataType": self._src.dtypes[i-1].title(), "band": str(i)})
            src = ET.SubElement(band, "SimpleSource")
            ET.SubElement(src, "SourceFilename").text = "HDF5:{}://image_data/{}/{}/{}".format(self._snapshot._filename, self._gid, node, level)
            ET.SubElement(src, "SourceBand").text =str(i)
            ET.SubElement(src, "SrcRect", {"xOff": "0", "yOff": "0",
                                           "xSize": str(self._roi.num_cols), "ySize": str(self._roi.num_rows)})
            ET.SubElement(src, "DstRect", {"xOff": "0", "yOff": "0",
                                           "xSize": str(self._roi.num_cols), "ySize": str(self._roi.num_rows)})

            ET.SubElement(src, "SourceProperties", {"RasterXSize": str(self._roi.num_cols), "RasterYSize": str(self._roi.num_rows),
                                                    "BlockXSize": "128", "BlockYSize": "128", "DataType": self._src.dtypes[i-1].title()})
        vrt_str = ET.tostring(vrt)


        vrt_file = self._vrt_file(node, level)
        with open(vrt_file, "w") as f:
            f.write(vrt_str)

        return vrt_file

    def _vrt_file(self, node, level):
        return os.path.join(self._vrt_dir, ".".join([self._gid, node, str(level) + ".vrt"]))

    def vrt(self, node="TOAReflectance", level="0"):
        vrt_file = self._vrt_file(node, level)
        if os.path.exists(vrt_file):
            return vrt_file
        print("fetching image from vrt, writing to snapshot file and generating vrt reference")
        return self.fetch(node=node, level=level)

class DGSnapshot(Snapshot):
    def __init__(self, snapfile, vrt_dir="/home/gremlin/project/.vst"):
        super(DGSnapshot, self).__init__(snapfile)
        self._vrt_dir = vrt_dir
        if not os.path.isdir(vrt_dir):
            os.mkdir(vrt_dir)
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
            self._lut[data["id"]] = WrappedGeoJSON(self, data=data, vrt_dir=self._vrt_dir)
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
