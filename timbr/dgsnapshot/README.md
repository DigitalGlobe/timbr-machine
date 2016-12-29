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
dgsnap = DGSnapshot('/path/to/<your_geojson_filename>.json', snapfile='output_snap.h5')
```

This will write each element of your feature set to the Snapshot array. You may optionally pass the output path to the snapfile; 
by default the file will be written to `/path/to/<your_geojson_filename>.h5`.


# Accessing data

Feature data can be accessed via indexing or iteration. The wrapped data that is returned can be inspected as usual:

```
>>> dgsnap[0]
{"geometry": {"type": "Polygon", "coordinates": ... "product_level": "LV1B"}}
```

Nested data can be accessed via keys like a normal dictionary, and returns the data object:

```
>>> geo = dgsnap[0]['geometry']

>>> geo
{'coordinates': [[[-77.07880205, 38.12225203], [-77.07880205, 38.26130324], ... 38.12225203]]], 'type': 'Polygon'}

>>> type(geo)
'dict'
```


# Fetching Images

Calling `fetch()` on a 



