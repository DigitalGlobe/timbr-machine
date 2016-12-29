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
dgsnap = DGSnapshot(/path/to/your_geojson.json)
```

