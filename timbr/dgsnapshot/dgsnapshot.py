from timbr.snapshot.snapshot import Snapshot
from timbr.machine import serializer

try:
    from io import BytesIO
except ImportError:
    from StringIO import cStringIO as BytesIO

import tables
import h5py

import os
import codecs
import sys
import json
import inspect
from functools import partial
from collections import defaultdict
from itertools import groupby
import threading
import contextlib
from IPython.display import display, Javascript

import warnings
warnings.filterwarnings('ignore')

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

from gbdxtools import Interface

from osgeo import gdal
gdal.UseExceptions()

NTHREAD_DEFAULT = 4
_num_workers = NTHREAD_DEFAULT

if "TIMBR_DGSNAP_NTHREAD" in os.environ:
    try:
        _num_workers = int(os.environ["TIMBR_DGSNAP_NTHREAD"])
    except ValueError as ve:
        os.environ["TIMBR_DGSNAP_NTHREAD"] = NTHREAD_DEFAULT

threaded_get = partial(dask.threaded.get, num_workers=_num_workers)
_curl_pool = defaultdict(pycurl.Curl)

class NotSupportedException(NotImplementedError):
    pass

def data_to_np(data):
    return np.fromstring(serializer.dumps(data), dtype="uint8")

def parse_bounds(raw):
    bounds = [float(n.strip()) for n in raw.split(",")]
    return bounds

def index_to_slice(ind, rowstep, colstep):
    i, j = ind
    window = ((i * rowstep, (i + 1) * rowstep), (j * colstep, (j + 1) * colstep))
    return window

def roi_from_bbox_projection(src, user_bounds, block_shapes=None, preserve_blocksize=True):
    roi = src.window(*user_bounds)
    if not preserve_blocksize:
        return roi
    if block_shapes is None:
        blocksafe_roi = rasterio.windows.round_window_to_full_blocks(roi, src.block_shapes)
    else:
        blocksafe_roi = rasterio.windows.round_window_to_full_blocks(roi, block_shapes)
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
def load_url(url, bands=8):
    #print('fetching', url)
    thread_id = threading.current_thread().ident
    _curl = _curl_pool[thread_id]
    buf = BytesIO()
    _curl.setopt(_curl.URL, url)
    _curl.setopt(_curl.WRITEDATA, buf)
    _curl.perform()

    with MemoryFile(buf.getvalue()) as memfile:
      try:
          with memfile.open(driver="GTiff") as dataset:
              arr = dataset.read()
      except (TypeError, rasterio.RasterioIOError) as e:
          print("Errored on {} with {}".format(url, e))
          arr = np.zeros([bands,256,256], dtype=np.float32)
          _curl.close()
          del _curl_pool[thread_id]
    return arr

def build_array(urls, bands=8):
    buf = da.concatenate(
        [da.concatenate([da.from_delayed(load_url(url, bands=bands), (bands,256,256), np.float32) for url in row],
                        axis=1) for row in urls], axis=2)
    return buf

def ms_to_rgb(mbimage):
    nbands, x, y = mbimage.shape
    if nbands == 8:
        rgb_uint8 = (np.dstack((mbimage[4,:,:], mbimage[2,:,:], mbimage[1,:,:])).clip(min=0) * 255.0).astype(np.uint8)
        return rgb_uint8
    return mbimage

class WrappedGeoJSON(dict):
    def __init__(self, snapshot, data, vrt_dir="/home/gremlin/vrt"):
        self.update(data)
        self._snapshot = snapshot
        self._gid = data["id"]
        self._vrt_dir = vrt_dir

    def __setitem__(self, key, value):
        raise NotSupportedException

    def __delitem__(self, key):
        raise NotSupportedException

    def fetch(self, node="TOAReflectance", level="0"):
        user_bounds = parse_bounds(self._snapshot["bounds"])
        self._user_bounds = user_bounds
        url = build_url(self._gid, node=node, level=level)
        self._url = url
        self._src = rasterio.open(url)
        block_shapes = [(256, 256) for bs in self._src.block_shapes]
        self._roi = roi_from_bbox_projection(self._src, user_bounds, block_shapes=block_shapes)

        window = self._roi.flatten()
        px_bounds = [window[0], window[1], window[0] + window[2], window[1] + window[3] ]
        self._px_bounds = px_bounds
        res = requests.get(url, params={"window": ",".join([str(c) for c in px_bounds])})
        tmp_vrt = os.path.join(self._vrt_dir, ".".join([".tmp", node, level, self._gid + ".vrt"]))
        with open(tmp_vrt, "w") as f:
            f.write(res.content)

        dpath = "/{}_{}_{}".format(self._gid, node, level)
        urls = collect_urls(tmp_vrt)
        darr = build_array(urls, bands=self._src.meta['count'])
        self._snapshot._fileh.close()

        print("Starting parallel fetching... {} chips".format(sum([len(x) for x in urls])))
        with dask.set_options(get=threaded_get):
            darr.to_hdf5(self._snapshot._filename, dpath)
        for key in _curl_pool.keys():
            _curl_pool[key].close()
            del _curl_pool[key]
        print("Fetch complete")

        self._snapshot._fileh = tables.open_file(self._snapshot._filename, mode='r') #reopen snapfile w pytables
        self._snapshot._raw = self._snapshot._fileh.root.raw

        vrt_file = self._generate_vrt(node=node, level=level)
        self._src.close()
        return vrt_file

    def _generate_vrt(self, node="TOAReflectance", level="0"):
        vrt = ET.Element("VRTDataset", {"rasterXSize": str(self._roi.num_cols),
                        "rasterYSize": str(self._roi.num_rows)})
        ET.SubElement(vrt, "SRS").text = str(self._src.crs['init']).upper()
        ET.SubElement(vrt, "GeoTransform").text = ", ".join([str(c) for c in self._src.get_transform()])
        for i in self._src.indexes:
            band = ET.SubElement(vrt, "VRTRasterBand", {"dataType": self._src.dtypes[i-1].title(), "band": str(i)})
            src = ET.SubElement(band, "SimpleSource")
            ET.SubElement(src, "SourceFilename").text = "HDF5:{}://{}_{}_{}".format(self._snapshot._filename, self._gid, node, level)
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

    @contextlib.contextmanager
    def open(self, node="TOAReflectance", level="0"):
        vrt_file = self._vrt_file(node, level)
        if os.path.exists(vrt_file):
            print(vrt_file)
            with rasterio.open(vrt_file) as src:
                yield src
        else:
            print("fetching image from vrt, writing to snapshot file and generating vrt reference")
            with rasterio.open(self.fetch(node=node, level=level)) as src:
                yield src

    def vrt(self, node="TOAReflectance", level="0"):
        return build_url(self._gid, node=node, level=level)

    def preview(self, gbdx_token=None, width=700, height=400):
        if gbdx_token is None:
            try:
                gbdx = Interface()
                gbdx_token = gbdx.gbdx_connection.access_token
                self.create_preview_map(gbdx_token, width=width, height=height)
            except:
                print("""Missing GBDX Credentials, try either passing in 'gbdx_token' or define GBDX environment vars:
                    import os
                    os.environ['GBDX_USERNAME'] = 'your username'
                    os.environ['GBDX_PASSWORD'] = 'your password'
                    os.environ['GBDX_CLIENT_ID'] = 'your client id'
                    os.environ['GBDX_CLIENT_SECRET'] = 'your client secrect'
                """)
        else:
            self.create_preview_map(gbdx_token, width=width, height=height)

    def read(self, bands=[], **kwargs):
        for band in bands:
            if not isinstance(band, int):
                raise TypeError("Band arguments must be passed as integers")
        with self.open(**kwargs) as src:
            if len(bands) > 0:
                return src.read(bands)
            return src.read()

    def create_preview_map(self, token, width=700, height=400):
        with rasterio.open(self.vrt()) as dataset:
            if dataset.meta['count'] == 8:
                bands = '4,2,1'
            else:
                bands = '0'

        bucket_name = 'idaho-images'
        idaho_id = self._gid
        try:
            W,S = self['geometry']['coordinates'][0][0]
            E,N = self['geometry']['coordinates'][0][2]
        except:
            W,S = self['geometry']['coordinates'][0][0][0]
            E,N = self['geometry']['coordinates'][0][0][2]
        functionstring = "addLayerToMap('%s','%s',%s,%s,%s,%s);\n" % (bucket_name, idaho_id, W, S, E, N)

        dir_name = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join( dir_name, 'leaflet_template.js'), 'r') as htmlfile:
            data=htmlfile.read().decode("utf8")

        data = data.replace('FUNCTIONSTRING',functionstring)
        data = data.replace('BANDS', bands)
        data = data.replace('TOKEN', token)
        data = data.replace('MINX', str(W))
        data = data.replace('MINY', str(S))
        data = data.replace('MAXX', str(E))
        data = data.replace('MAXY', str(N))
        return display(Javascript(data), width=width, height=height)

    def to_geotiff(self, node="TOAReflectance", level="0"):
        im = self.read(node=node, level=level)
        nbands, height, width = im.shape
        if nbands == 8:
            rgb = ms_to_rgb(im)
            rgb = np.rollaxis(rgb, 2, 0)
        elif nbands == 1:
            rgb = im
        else:
            raise TypeError
        if path is None:
            path = os.path.join(self._vrt_dir, ".".join([self._gid, node, level]) + ".tif")
        with rasterio.open(path, "w",
                           driver="GTiff",
                           width=width,
                           height=height,
                           dtype=rgb.dtype,
                           count=nbands) as dst:
            dst.write(rgb)

class DGSnapshot(Snapshot):
    def __init__(self, snapfile, vrt_dir="/home/gremlin/.vrt"):
        super(DGSnapshot, self).__init__(snapfile)
        self._vrt_dir = vrt_dir
        if not os.path.isdir(vrt_dir):
            os.mkdir(vrt_dir)
        self._lut = {}

    def __getitem__(self, spec):
        if isinstance(spec, (int, long)):
            return self._wrap_data(self._input_fn(self._raw[spec].tostring()))
        elif spec in ("type", "bounds"):
            return self.raw.attrs[spec]
        else:
            return list(self.__iter__(spec))

    def __iter__(self, specs=slice(None)):
        if isinstance(specs, slice):
            for rec in self._raw.iterrows(specs.start, specs.stop, specs.step):
                yield self._wrap_data(self._input_fn(rec.tostring()))
        else:
            for rec in self._raw[spec]:
                yield self._wrap_data(self._input_fn(rec.tostring()))

    def _wrap_data(self, data):
        if data["id"] not in self._lut:
            self._lut[data["id"]] = WrappedGeoJSON(self, data, vrt_dir=self._vrt_dir)
        return self._lut[data["id"]]

    @classmethod
    def from_geojson(cls, geojsonfile, snapfile=None, bounds=None, **kwargs):
        with open(geojsonfile) as f:
            geojson = json.load(f)
        if snapfile is None:
            fn = os.path.splitext(geojsonfile)[0]
            snapfile = fn + ".h5"
        elif os.path.splitext(snapfile)[-1] != ".h5":
            snapfile = snapfile + ".h5"

        if os.path.exists(snapfile):
            inst = cls(snapfile, **kwargs)
            if inst._fileh.root.raw.attrs.bounds == geojson["bounds"]:
                return inst
            inst.close()
            raise IOError("The file {} already exists and was created with different coordinate bounds. Delete this file before creating a new one.".format(snapfile))

        snap = tables.open_file(snapfile, "a")
        raw = snap.create_vlarray(snap.root, "raw", atom=tables.UInt8Atom(shape=()), filters=tables.Filters(complevel=0))
        features = geojson["features"]
        for f in features:
            raw.append(data_to_np(f))
        raw.attrs.type = geojson["type"]
        try:
            raw.attrs.bounds = geojson["bounds"]
        except KeyError as ke:
            if bounds is not None:
                raw.attrs.bounds = bounds
        snap.close()

        snap = h5py.File(snapfile)
        dummy_image = np.ones((100,100), dtype=np.int)
        ds = snap.create_dataset('/dummy', dummy_image.shape, np.int)
        ds[:,:] = dummy_image

        snap.flush()
        snap.close()
        return cls(snapfile, **kwargs)
