requirejs.config( {
    paths: { 
      leaflet: "https://npmcdn.com/leaflet@1.0.0-rc.3/dist/leaflet",
      leaflet_draw: "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/0.4.9/leaflet.draw"
    }
  }
);

requirejs(["leaflet", "leaflet_draw"], function( leaflet, leaflet_draw ) {
    var link = document.createElement("link");
    link.type = "text/css";
    link.rel = "stylesheet";
    link.href = "https://npmcdn.com/leaflet@1.0.0-rc.3/dist/leaflet.css";
    document.getElementsByTagName("head")[0].appendChild(link);

    var div = document.createElement("div");
    div.id = 'map';
    element.append(div);
   
    var css = "#map { height: 400px;  width: 100%; z-index: 100; } .leaflet-control-container { text-decoration: none; } img.leaflet-tile { margin:0px; }";
    var head = document.head || document.getElementsByTagName('head')[0];
    var style = document.createElement('style');

    style.type = 'text/css';
    if (style.styleSheet){
      style.styleSheet.cssText = css;
    } else {
      style.appendChild(document.createTextNode(css));
    }
    head.appendChild(style);
 
    var mymap = L.map('map');
    L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpandmbXliNDBjZWd2M2x6bDk3c2ZtOTkifQ._QA7i5Mpkd_m30IGElHziw', {
      maxZoom: 18,
      attribution: 'Map data &copy; <a href="http://openstreetmap.org">OpenStreetMap</a> contributors, ' +
        '<a href="http://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
        'Imagery © <a href="http://mapbox.com">Mapbox</a>',
      id: 'mapbox.streets'
    }).addTo(mymap);
    var token = 'TOKEN';
    var bands = 'BANDS';
    var gamma = '1.3';
    var highCutoff = '0.98';
    var lowCutoff = '0.02';
    var brightness = '1.0';
    var contrast = '1.0';
    var tmsRootUrl = 'http://idaho.geobigdata.io/v1/'
    function addLayerToMap(bucketName, imageId, W, S, E, N, panImageId) {
      var southWest = L.latLng(S,W),
          northEast = L.latLng(N,E),
          bounds = L.latLngBounds(southWest, northEast);
          var tmsUrl = tmsRootUrl+"tile/"+bucketName+'/'+imageId+'/{z}/{x}/{y}?bands='+bands+'&gamma='+gamma+'&highCutoff='+highCutoff+'&lowCutoff='+lowCutoff+'&brightness='+brightness+'&contrast='+contrast+'&token='+token;
      if(panImageId !== ""){
            tmsUrl = tmsUrl+'&panId='+panImageId;
          }
      var tmsLayer = new L.TileLayer(tmsUrl, {minZoom: 10, maxZoom: 20, bounds:bounds});
          tmsLayer.isBaseLayer=false;
          mymap.addLayer(tmsLayer);
    }
    FUNCTIONSTRING
    mymap.fitBounds([[MINY, MINX],[MAXY, MAXX]]);
});
