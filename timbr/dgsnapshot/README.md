## DGSnapshot Overview

`DGSnapshot` implements a subclass of `timbr.snapshot.Snapshot` that can be used to fetch and store imagery given a set of GeoJSON
features. The interface for reading geoJSON data from `DGSnapshot` is similar to `timbr.snapshot.Snapshot`, except that accessing 
data returns an instance of `WrappedGeoJSON` to the user, providing two instance attributes, `fetch()` and `vrt` 
that can be utilized for accessing, writing and reading image data.


# Creating a DGSnapshot

Currently the best way to create a DGSnapshot is from an onhand geoJSON file using the `.from_geojson` classmethod:

```Python
from timbr.dgsnapshot import DGSnapshot

# Create a DGSnapshot from a geoJSON file containing a set of features
dgsnap = DGSnapshot.from_geojson('/path/to/<your_geojson_filename>.json', snapfile='output_snap.h5')
```

This will write each element of your feature set to the Snapshot array. You may optionally pass the output path to the snapfile; 
by default the file will be written to `/path/to/<your_geojson_filename>.h5`.


# Accessing data

Feature data can be accessed via indexing or iteration. The wrapped data that is returned can be inspected as usual:

```
>>> dgsnap[0]
{"geometry": {"type": "Polygon", "coordinates": ... "product_level": "LV1B"}}
```

The wrapped data behaves like a dictionary:

```
>>> dgsnap[0].keys()
['geometry']
```


# Fetching Images

Calling `fetch()` on some wrapped geoJSON data attempts to write image data to your snapshot corresponding to your feature by 
performing the following steps:

1. Build the appropriate url for accessing the relevant .vrt file hosted at http://idaho.timbr.io
2. If this file exists, open it and read the raster window corresponding to the intersection of the geoJSON feature and the raster image
3. Write this data to the snapshot file at the hdf5 path `/image_data/<feature_id>`
4. Create a local .vrt file that containing the appropriate metadata that references the location of the image in the snapfile

Step 2 of the above process can potentially take a long time to complete due to the fact that the accessed vrt file may reference hundreds
or thousands of different image paths corresponding to chunks of the final raster. Multithreaded or Multiprocessing read options will be 
available in the future to mitigate read completion times.

# Reading Images

Once `fetch()` has been called, images can be read directly from an index via the `vrt` attribute using a relevant library like 
`rasterio` or `gdal`:

```Python
import rasterio

with rasterio.open(dgsnap[0].vrt) as src:
	image = src.read()
```

If you image data is multi-banded, this will return a numpy array with the shape `(num_bands, num_rows, num_cols)`. In the event that the reference vrt 
file cannot be found, `fetch()` will be called in an attempt to create it after fetching and writing the raster.



