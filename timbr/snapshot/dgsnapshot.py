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

def write_image_from_vrt(vrtfile, user_bounds, snapfile="test.h5", chunked=True):
    with rasterio.open(vrtfile) as src:
        roi = roi_from_bbox_projection(src, user_bounds)
        if not chunked:
            read_win = ((roi.row_off, roi.num_rows), (roi.col_off, roi.num_cols))
            for i in src.indexes:
                data = src.read(i, window = read_window)
                # write to snapshot here
        else:
            for i in src.indexes:
                for chunk in generate_blocks(roi, src.block_shapes[0]):
                    data = src.read(i, window = chunk)
                    # write to snapshot here
                    
    return snapfile
            
        
def roi_from_bbox_projection(src, userbounds, preserve_blocksize=True):
    """ 
    Calculate the intersection of a bounding box and a raster window by projecting the bounding box 
    onto the raster coordinate grid. The resulting subwindow is the intersection of the bbox and the 
    raster window defined as a function of the raster window. If preserve_blocksize is True, the subwindow
    domain may be minimally extended along one or both axes into the raster window to ensure that the 
    resulting shape can be partitioned into an integer number of raster blocks.
    """
    roi = src.window(*userbounds)
    if not preserve_blocksize:
        return roi
    blocksafe_roi = rasterio.windows.round_window_to_full_blocks(roi, src.block_shapes)
    return blocksafe_roi

def generate_blocks(window, blocksize):
    """
    Return a generator that yields window blocks sequentially over axis[0].
    """
    if blocksize[0] != blocksize[1]:
        raise NotImplementedError
    bsize = blocksize[0]
    assert window.num_rows % bsize == 0
    assert window.num_cols % bsize == 0
    nrowblocks = window.num_rows / bsize
    ncolblocks = window.num_cols / bsize
    for ind in np.ndindex((nrowblocks, ncolblocks)):
        yield index_to_slice(ind, nrowblocks, ncolblocks)
        
def fetch(vrtfile, base_url="http://idaho.timbr.io", node="TOAReflectance", level=0):
    relpath = "/".join([self.gid, node, str(level) + ".vrt"])
    url = urljoin(base_url, relpath)
    res = requests.get(url)
    if res.status_code != 200:
        res.raise_for_status()
    #write the vrt to a file
    with open(vrtfile, "w") as f:
        f.write(res.content)
    return vrtfile
    
class WrappedData(object):
    def __init__(self, snapshot, data, vrt_dir="/home/gremlin/vrt"):
        self.snapshot = snapshot
        self.data = data
        self.gid = data["id"]
        self._tmpfn = os.path.join(self.snapshot._vst_dir, ".tmp-{}.vrt".format(self.gid))
        self._refvrt = None
        
    def __repr__(self):
        return json.dumps(self.data)
    
    def __getitem__(self, item):
        return self.data[item]

    def fetch(self, **kwargs):
        vrtfile = fetch(self._tmpfn, **kwargs)
        user_bounds = parse_bounds(self.snapshot["bounds"]["bounds"])
        # Read and write the data:
        snapfile = write_image_from_vrt(vrtfile, user_bounds)
        refvrt = write_reference_vrt(snapfile)
        self._refvrt = refvrt
        return refvrt
        
    @property
    def vrt(self):
        if self._refvrt is not None:
            return self._refvrt
        print("fetching image from vrt, writing to snapshot file and generating vrt reference")
        return self.fetch()
        
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
        
    def __iter__(self, specs=slice(None)):
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
        raw.attrs.bounds = data_to_np({"bounds": geojson["bounds"]})
        snap.close()
        return cls(snapfile, **kwargs) 
